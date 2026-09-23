#!/usr/bin/env python3
"""Normalize Codex usage data into a durable workflow flow-control record.

This module deliberately has no network or authentication dependency.  A caller
supplies the JSON returned by Codex's ``account/rateLimits/read`` app-server
method (or a deterministic fixture), and this script turns it into a small,
atomic JSON record that a workflow supervisor can read before scheduling work.

The app-server response has a legacy ``rateLimits`` snapshot and, on newer
accounts, a ``rateLimitsByLimitId`` map.  The latter is authoritative whenever
it is present because different models can be metered against different quota
buckets.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping


SCHEMA_VERSION = 1
DEFAULT_WARNING_HEADROOM_PERCENT = 15.0
DEFAULT_SUSPEND_HEADROOM_PERCENT = 10.0
DEFAULT_APP_SERVER_TIMEOUT_SECONDS = 10.0
MAX_APP_SERVER_TIMEOUT_SECONDS = 30.0
APP_SERVER_CLIENT_INFO = {
    "name": "ai-workflow-usage-guard",
    "title": "AI Workflow Usage Guard",
    "version": "1",
}
MAX_APP_SERVER_STDERR_CHARS = 1_000


class AppServerReadError(ValueError):
    """A bounded app-server read could not produce a trustworthy response."""


def _mapping(value: Any) -> Mapping[str, Any] | None:
    """Return ``value`` as a mapping, without accepting mapping-like objects."""

    return value if isinstance(value, Mapping) else None


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _percent(value: Any, field: str) -> float:
    result = _number(value, field)
    if not 0.0 <= result <= 100.0:
        raise ValueError(f"{field} must be between 0 and 100")
    return result


def _epoch_seconds(value: Any, field: str) -> int | None:
    """Convert an app-server Unix timestamp to integer seconds.

    App-server timestamps are seconds.  Accepting millisecond fixtures too is
    harmless and makes the reader robust to relay implementations that retain
    JavaScript timestamps without converting them first.
    """

    if value is None:
        return None
    number = _number(value, field)
    if number < 0:
        raise ValueError(f"{field} must not be negative")
    if number >= 100_000_000_000:
        number /= 1000
    return int(number)


def _duration_minutes(value: Any, field: str) -> int | None:
    if value is None:
        return None
    result = _number(value, field)
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return int(result)


def _unwrap_rate_limit_payload(payload: Any) -> Mapping[str, Any]:
    """Find a rate-limit response inside common app-server/MCP envelopes."""

    current = _mapping(payload)
    if current is None:
        raise ValueError("rate-limit payload must be a JSON object")

    # The direct app-server response is the normal case.  The extra wrappers
    # make saved JSON-RPC and tool fixtures convenient without making callers
    # rewrite them.
    for _ in range(4):
        if "rateLimits" in current or "rateLimitsByLimitId" in current:
            return current
        nested = None
        for key in ("result", "structuredContent", "params", "data"):
            candidate = _mapping(current.get(key))
            if candidate is not None:
                nested = candidate
                break
        if nested is None:
            break
        current = nested
    raise ValueError("payload does not contain rateLimits or rateLimitsByLimitId")


def _normalize_window(limit_id: str, window_name: str, window: Mapping[str, Any]) -> dict[str, Any]:
    if "usedPercent" not in window:
        raise ValueError(f"{limit_id}.{window_name}.usedPercent is required")
    used_percent = _percent(window["usedPercent"], f"{limit_id}.{window_name}.usedPercent")
    return {
        "id": f"{limit_id}:{window_name}",
        "limit_id": limit_id,
        "window": window_name,
        "used_percent": used_percent,
        "remaining_percent": 100.0 - used_percent,
        "resets_at_epoch": _epoch_seconds(window.get("resetsAt"), f"{limit_id}.{window_name}.resetsAt"),
        "window_duration_minutes": _duration_minutes(
            window.get("windowDurationMins"), f"{limit_id}.{window_name}.windowDurationMins"
        ),
    }


def _normalize_snapshot(
    limit_id: str, snapshot: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, bool], list[str]]:
    windows: list[dict[str, Any]] = []
    unavailable_window_ids: list[str] = []
    for window_name in ("primary", "secondary"):
        if window_name not in snapshot:
            unavailable_window_ids.append(f"{limit_id}:{window_name}")
            continue
        window_value = snapshot[window_name]
        if window_value is None:
            # App-server documents nullable secondary windows. Preserve that
            # uncertainty in the flow record rather than mistaking it for a
            # zero-use quota or rejecting an otherwise usable primary window.
            unavailable_window_ids.append(f"{limit_id}:{window_name}")
            continue
        window = _mapping(window_value)
        if window is None:
            raise ValueError(f"{limit_id}.{window_name} must be an object or null")
        windows.append(_normalize_window(limit_id, window_name, window))
    flags = {
        "rate_limit_reached": bool(snapshot.get("rateLimitReachedType")),
        "spend_control_reached": snapshot.get("spendControlReached") is True,
    }
    return windows, flags, unavailable_window_ids


def normalize_codex_rate_limits(payload: Any) -> dict[str, Any]:
    """Normalize a Codex app-server rate-limit payload.

    The returned structure is deliberately provider-neutral enough for a flow
    controller, while retaining every per-limit primary/secondary window.
    ``rateLimitsByLimitId`` wins over the legacy single-bucket view so the same
    quota is never double-counted.
    """

    response = _unwrap_rate_limit_payload(payload)
    raw_buckets_by_id = response.get("rateLimitsByLimitId")
    if raw_buckets_by_id is None:
        buckets_by_id: Mapping[str, Any] | None = None
    else:
        buckets_by_id = _mapping(raw_buckets_by_id)
        if buckets_by_id is None:
            raise ValueError("rateLimitsByLimitId must be an object or null")
        if not buckets_by_id:
            raise ValueError("rateLimitsByLimitId must not be empty when present")
    snapshots: list[tuple[str, Mapping[str, Any]]] = []
    source = "legacy"

    if buckets_by_id:
        source = "multi_bucket"
        for map_limit_id in sorted(buckets_by_id):
            snapshot = _mapping(buckets_by_id[map_limit_id])
            if snapshot is None:
                raise ValueError(f"rateLimitsByLimitId.{map_limit_id} must be an object")
            limit_id = snapshot.get("limitId")
            if not isinstance(limit_id, str) or not limit_id:
                limit_id = map_limit_id
            if not isinstance(limit_id, str) or not limit_id:
                raise ValueError("rate limit identifier must be a non-empty string")
            snapshots.append((limit_id, snapshot))
    else:
        legacy = _mapping(response.get("rateLimits"))
        if legacy is None:
            raise ValueError("rateLimits must be an object when rateLimitsByLimitId is unavailable")
        limit_id = legacy.get("limitId")
        if not isinstance(limit_id, str) or not limit_id:
            limit_id = "legacy"
        snapshots.append((limit_id, legacy))

    windows: list[dict[str, Any]] = []
    unavailable_window_ids: list[str] = []
    reached = False
    spend_control_reached = False
    for limit_id, snapshot in snapshots:
        snapshot_windows, flags, unavailable = _normalize_snapshot(limit_id, snapshot)
        windows.extend(snapshot_windows)
        unavailable_window_ids.extend(unavailable)
        reached = reached or flags["rate_limit_reached"]
        spend_control_reached = spend_control_reached or flags["spend_control_reached"]

    if not windows:
        raise ValueError("rate-limit response contains no primary or secondary windows")

    windows.sort(key=lambda window: window["id"])
    ordinary_usage_allowed = response.get("ordinaryUsageAllowed")
    if ordinary_usage_allowed is not None and not isinstance(ordinary_usage_allowed, bool):
        raise ValueError("ordinaryUsageAllowed must be a boolean or null")
    return {
        "provider": "codex",
        "source": source,
        "ordinary_usage_allowed": ordinary_usage_allowed,
        "rate_limit_reached": reached,
        "spend_control_reached": spend_control_reached,
        "unavailable_window_ids": sorted(unavailable_window_ids),
        "windows": windows,
    }


def _iso_timestamp(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_thresholds(warning_headroom_percent: float, suspend_headroom_percent: float) -> tuple[float, float]:
    warning = _percent(warning_headroom_percent, "warning headroom percent")
    suspend = _percent(suspend_headroom_percent, "suspend headroom percent")
    if suspend > warning:
        raise ValueError("suspend headroom percent must not exceed warning headroom percent")
    return warning, suspend


def _resume_time(windows: list[dict[str, Any]], now_epoch: int) -> tuple[int | None, bool]:
    """Return a safe reset time and whether every limiting window supplies one."""

    resets = [window["resets_at_epoch"] for window in windows]
    if any(reset is None for reset in resets):
        return None, False
    # Every currently limiting quota must recover before a new worker is
    # launched.  A scheduler must still refresh the provider data at this time.
    return max(now_epoch, max(int(reset) for reset in resets if reset is not None)), True


def evaluate_codex_usage(
    normalized: Mapping[str, Any],
    *,
    warning_headroom_percent: float = DEFAULT_WARNING_HEADROOM_PERCENT,
    suspend_headroom_percent: float = DEFAULT_SUSPEND_HEADROOM_PERCENT,
    now_epoch: int | float | None = None,
) -> dict[str, Any]:
    """Evaluate normalized Codex usage against warning and suspension policy.

    ``SUSPENDED`` means scheduling should pause until ``resume_at_epoch`` and
    then obtain a fresh usage read.  ``BLOCKED`` means a reliable resume time
    is unavailable or a spend-control limit needs explicit handling.
    """

    warning, suspend = _validate_thresholds(warning_headroom_percent, suspend_headroom_percent)
    current_epoch = int(time.time() if now_epoch is None else _number(now_epoch, "now epoch"))
    raw_windows = normalized.get("windows")
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ValueError("normalized usage must contain at least one window")
    windows = [dict(window) for window in raw_windows if isinstance(window, Mapping)]
    if len(windows) != len(raw_windows):
        raise ValueError("normalized usage windows must be objects")

    hard_windows = [window for window in windows if _percent(window.get("remaining_percent"), "remaining_percent") <= suspend]
    warning_windows = [window for window in windows if _percent(window.get("remaining_percent"), "remaining_percent") <= warning]
    reached = normalized.get("rate_limit_reached") is True
    ordinary_usage_allowed = normalized.get("ordinary_usage_allowed")
    spend_control_reached = normalized.get("spend_control_reached") is True

    state = "OK"
    reason = "headroom_ok"
    limiting_windows: list[dict[str, Any]] = []
    requires_fresh_check = False
    resume_at_epoch: int | None = None

    if spend_control_reached:
        state = "BLOCKED"
        reason = "spend_control_reached"
        limiting_windows = windows
        requires_fresh_check = True
    elif hard_windows or reached or ordinary_usage_allowed is False:
        # A backend-declared reached/disallowed state has priority even if a
        # rolling notification has not yet updated all percentage fields.
        state = "SUSPENDED"
        if ordinary_usage_allowed is False:
            reason = "ordinary_usage_disallowed"
        elif reached:
            reason = "rate_limit_reached"
        else:
            reason = "headroom_at_or_below_suspend_threshold"
        limiting_windows = hard_windows or windows
        resume_at_epoch, has_resume_time = _resume_time(limiting_windows, current_epoch)
        requires_fresh_check = True
        if not has_resume_time:
            state = "BLOCKED"
            reason = "suspend_without_reset_time"
    elif warning_windows:
        state = "WARNING"
        reason = "headroom_at_or_below_warning_threshold"
        limiting_windows = warning_windows

    compact_windows = [
        {
            "id": window["id"],
            "remaining_percent": _percent(window.get("remaining_percent"), "remaining_percent"),
            "resets_at_epoch": window.get("resets_at_epoch"),
        }
        for window in windows
    ]
    compact_windows.sort(key=lambda window: window["id"])
    limiting_ids = sorted(str(window["id"]) for window in limiting_windows)
    unavailable_window_ids = normalized.get("unavailable_window_ids", [])
    if not isinstance(unavailable_window_ids, list) or not all(isinstance(value, str) for value in unavailable_window_ids):
        raise ValueError("normalized unavailable window identifiers must be a list of strings")
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "codex",
        "state": state,
        "reason": reason,
        "observed_at_epoch": current_epoch,
        "warning_headroom_percent": warning,
        "suspend_headroom_percent": suspend,
        "resume_at_epoch": resume_at_epoch,
        "resume_at_iso": _iso_timestamp(resume_at_epoch),
        "requires_fresh_check": requires_fresh_check,
        "limiting_window_ids": limiting_ids,
        "unavailable_window_ids": sorted(unavailable_window_ids),
        "windows": compact_windows,
    }


def atomic_write_json(path: Path, record: Mapping[str, Any]) -> None:
    """Atomically replace a flow-control JSON file with a compact record."""

    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(record, handle, sort_keys=True, separators=(",", ":"), allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        try:
            directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _validate_app_server_timeout(value: Any) -> float:
    timeout = _number(value, "app-server timeout seconds")
    if timeout <= 0.0 or timeout > MAX_APP_SERVER_TIMEOUT_SECONDS:
        raise AppServerReadError(
            f"app-server timeout seconds must be greater than 0 and at most {MAX_APP_SERVER_TIMEOUT_SECONDS:g}"
        )
    return timeout


def _write_json_rpc(process: subprocess.Popen[str], message: Mapping[str, Any]) -> None:
    if process.stdin is None:
        raise AppServerReadError("app-server stdin is unavailable")
    try:
        process.stdin.write(json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError) as error:
        raise AppServerReadError(f"app-server closed stdin: {error}") from error


def _start_app_server_reader(process: subprocess.Popen[str]) -> queue.Queue[tuple[str, str]]:
    """Read app-server JSONL asynchronously so every response wait is bounded."""

    messages: queue.Queue[tuple[str, str]] = queue.Queue()

    def read_stdout() -> None:
        try:
            if process.stdout is None:
                messages.put(("error", "app-server stdout is unavailable"))
                return
            for line in process.stdout:
                messages.put(("line", line))
        except OSError as error:
            messages.put(("error", f"app-server stdout read failed: {error}"))
        finally:
            messages.put(("eof", ""))

    threading.Thread(target=read_stdout, name="usage-guard-app-server-reader", daemon=True).start()
    return messages


def _app_server_error_text(error: Any) -> str:
    error_mapping = _mapping(error)
    if error_mapping is None:
        return "unknown JSON-RPC error"
    message = error_mapping.get("message")
    if isinstance(message, str) and message:
        return message[:300]
    code = error_mapping.get("code")
    return f"JSON-RPC error {code!r}"[:300]


def _wait_for_json_rpc_result(
    messages: queue.Queue[tuple[str, str]],
    request_id: int,
    deadline: float,
) -> Any:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AppServerReadError(f"app-server request {request_id} timed out")
        try:
            kind, value = messages.get(timeout=remaining)
        except queue.Empty as error:
            raise AppServerReadError(f"app-server request {request_id} timed out") from error
        if kind == "error":
            raise AppServerReadError(value)
        if kind == "eof":
            raise AppServerReadError(f"app-server exited before response {request_id}")
        if len(value) > 1_000_000:
            raise AppServerReadError("app-server emitted an oversized JSONL message")
        try:
            message = json.loads(value)
        except json.JSONDecodeError as error:
            raise AppServerReadError(f"app-server emitted invalid JSON: {error.msg}") from error
        response = _mapping(message)
        if response is None:
            raise AppServerReadError("app-server emitted a non-object JSON-RPC message")
        if response.get("id") != request_id:
            # Notifications and responses to other server activity are not a
            # substitute for the bounded request we issued.
            continue
        if "error" in response:
            raise AppServerReadError(f"app-server request {request_id} failed: {_app_server_error_text(response['error'])}")
        if "result" not in response:
            raise AppServerReadError(f"app-server response {request_id} has neither result nor error")
        return response["result"]


def _stop_app_server(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _closed_app_server_stderr(process: subprocess.Popen[str] | None) -> str:
    """Return a bounded diagnostic after the short-lived child is stopped."""

    if process is None or process.stderr is None:
        return ""
    try:
        detail = process.stderr.read()
    except OSError:
        return ""
    detail = detail.strip()
    return detail[-MAX_APP_SERVER_STDERR_CHARS:]


def read_codex_app_server(codex_binary: str, timeout_seconds: float = DEFAULT_APP_SERVER_TIMEOUT_SECONDS) -> Any:
    """Read one rate-limit snapshot through a short-lived local app-server.

    This function is deliberately opt-in at the CLI level. It issues only the
    required JSONL handshake and one read-only account/rateLimits/read request;
    it never logs in, starts a thread, or mutates account state.
    """

    if not isinstance(codex_binary, str) or not codex_binary:
        raise AppServerReadError("codex binary must be a non-empty executable path")
    timeout = _validate_app_server_timeout(timeout_seconds)
    deadline = time.monotonic() + timeout
    process: subprocess.Popen[str] | None = None
    result: Any = None
    failure: AppServerReadError | None = None
    try:
        process = subprocess.Popen(
            [codex_binary, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        messages = _start_app_server_reader(process)
        _write_json_rpc(
            process,
            {
                "method": "initialize",
                "id": 1,
                "params": {"clientInfo": APP_SERVER_CLIENT_INFO},
            },
        )
        _wait_for_json_rpc_result(messages, 1, deadline)
        _write_json_rpc(process, {"method": "initialized", "params": {}})
        _write_json_rpc(process, {"method": "account/rateLimits/read", "id": 2})
        result = _wait_for_json_rpc_result(messages, 2, deadline)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, AppServerReadError):
            failure = error
        else:
            failure = AppServerReadError(f"app-server read failed: {error}")
    finally:
        _stop_app_server(process)
    if failure is not None:
        stderr = _closed_app_server_stderr(process)
        if stderr:
            raise AppServerReadError(f"{failure}; app-server stderr: {stderr}") from failure
        raise failure
    return result


def _safe_now_epoch(now_epoch: int | float | None) -> int:
    """Return a real clock value when invalid CLI input triggered the fallback."""

    if now_epoch is None:
        return int(time.time())
    try:
        return int(_number(now_epoch, "now epoch"))
    except ValueError:
        return int(time.time())


def _blocked_record(reason: str, now_epoch: int | float | None) -> dict[str, Any]:
    current_epoch = _safe_now_epoch(now_epoch)
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": "codex",
        "state": "BLOCKED",
        "reason": reason,
        "observed_at_epoch": current_epoch,
        "warning_headroom_percent": DEFAULT_WARNING_HEADROOM_PERCENT,
        "suspend_headroom_percent": DEFAULT_SUSPEND_HEADROOM_PERCENT,
        "resume_at_epoch": None,
        "resume_at_iso": None,
        "requires_fresh_check": True,
        "limiting_window_ids": [],
        "unavailable_window_ids": [],
        "windows": [],
    }


def _read_json_fixture(path_value: str) -> Any:
    if path_value == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_value).expanduser().read_text(encoding="utf-8"))


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a Codex usage flow-control record from JSON input.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="app-server JSON response fixture, or - for stdin")
    source.add_argument(
        "--read-codex-app-server",
        action="store_true",
        help="opt in to one bounded read-only local codex app-server request",
    )
    parser.add_argument("--flow-control", required=True, help="destination JSON flow-control record")
    parser.add_argument(
        "--codex-binary",
        default="codex",
        help="Codex executable used only with --read-codex-app-server (default: codex)",
    )
    parser.add_argument(
        "--app-server-timeout-seconds",
        type=float,
        default=DEFAULT_APP_SERVER_TIMEOUT_SECONDS,
        help=f"bounded app-server handshake/read timeout in seconds, 0-{MAX_APP_SERVER_TIMEOUT_SECONDS:g} (default: 10)",
    )
    parser.add_argument(
        "--warning-headroom-percent",
        type=float,
        default=DEFAULT_WARNING_HEADROOM_PERCENT,
        help="warn when remaining usage is at or below this percent (default: 15)",
    )
    parser.add_argument(
        "--suspend-headroom-percent",
        type=float,
        default=DEFAULT_SUSPEND_HEADROOM_PERCENT,
        help="suspend when remaining usage is at or below this percent (default: 10)",
    )
    parser.add_argument("--now-epoch", type=float, help="override clock for deterministic fixtures")
    return parser


def main(argv: list[str]) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        if args.read_codex_app_server:
            payload = read_codex_app_server(args.codex_binary, args.app_server_timeout_seconds)
        else:
            payload = _read_json_fixture(args.input)
        normalized = normalize_codex_rate_limits(payload)
        record = evaluate_codex_usage(
            normalized,
            warning_headroom_percent=args.warning_headroom_percent,
            suspend_headroom_percent=args.suspend_headroom_percent,
            now_epoch=args.now_epoch,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        # A corrupt or incomplete provider response must not leave a stale OK
        # record behind.  Persist a conservative state for guards to honor.
        record = _blocked_record(f"invalid_usage_input:{error}", args.now_epoch)
        atomic_write_json(Path(args.flow_control), record)
        print(json.dumps(record, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    atomic_write_json(Path(args.flow_control), record)
    print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
