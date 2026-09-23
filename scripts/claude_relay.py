#!/usr/bin/env python3
"""Bounded relay for a Claude JSONL worker stream.

The relay deliberately separates a worker's full event stream from the data a
workflow controller consumes:

* ``claude-events.jsonl`` retains every stdout line for later inspection.
* ``worker-status.json`` is a small, atomically replaced status snapshot.
* ``flow-control.json`` is a small, atomically replaced usage signal.

No model is involved in this module.  A controller may run a Claude command
through :func:`run`, or feed already-read JSONL lines into :class:`ClaudeRelay`
when it owns process lifecycle itself.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from typing import Any


SCHEMA_VERSION = 1
STATUS_FILENAME = "worker-status.json"
FLOW_CONTROL_FILENAME = "flow-control.json"
STREAM_FILENAME = "claude-events.jsonl"

# These limits apply to controller-facing data only.  The raw JSONL log remains
# complete on disk so a large changed-file list is inspectable without being
# sent through an MCP/tool result or a parent-agent context.
DEFAULT_CHANGED_FILE_SAMPLE_LIMIT = 20
MAX_FILE_PATH_CHARS = 160
MAX_TEXT_SUMMARY_CHARS = 600
MAX_CALLER_SUMMARY_CHARS = 4_096
MAX_EVENT_TYPE_CHARS = 80
MAX_SESSION_ID_CHARS = 256
MAX_STDERR_SUMMARY_CHARS = 4_096
DEFAULT_STALL_TIMEOUT_SECONDS = 1_800.0


def utc_timestamp() -> str:
    """Return an unambiguous timestamp suitable for durable status records."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def bounded_text(value: object, limit: int) -> str:
    """Convert *value* to text without permitting an unbounded status file."""

    if limit < 1:
        raise ValueError("limit must be positive")
    text = value if isinstance(value, str) else str(value)
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically replace a JSON file after fully flushing its temporary copy."""

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        # fsyncing the directory makes the rename durable on POSIX filesystems.
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            except OSError:
                pass
            finally:
                os.close(directory_descriptor)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def wall_timeout_deadline(start_monotonic: float, timeout_seconds: float | None) -> float | None:
    """Return a monotonic deadline, validating the relay's wall-time limit."""

    if timeout_seconds is None:
        return None
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when supplied")
    return start_monotonic + timeout_seconds


def wall_timeout_expired(
    start_monotonic: float, timeout_seconds: float | None, *, now_monotonic: float | None = None
) -> bool:
    """Whether a process started at *start_monotonic* has exceeded its wall limit."""

    deadline = wall_timeout_deadline(start_monotonic, timeout_seconds)
    return deadline is not None and (time.monotonic() if now_monotonic is None else now_monotonic) >= deadline


def _normalised_key(key: object) -> str:
    return "".join(character for character in str(key).lower() if character.isalnum())


def _mapping_value(mapping: Mapping[str, Any], *names: str) -> Any:
    entry = _mapping_entry(mapping, *names)
    return entry[1] if entry is not None else None


def _mapping_entry(mapping: Mapping[str, Any], *names: str) -> tuple[str, Any] | None:
    """Return the matched normalized key as well as its value."""

    wanted = {_normalised_key(name) for name in names}
    for key, value in mapping.items():
        normalized_key = _normalised_key(key)
        if normalized_key in wanted:
            return normalized_key, value
    return None


def _number(value: object, *, fraction_is_percent: bool = False) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip().rstrip("%")
        try:
            number = float(stripped)
        except ValueError:
            return None
    else:
        return None
    if fraction_is_percent and 0 <= number <= 1:
        number *= 100
    return min(100.0, max(0.0, number))


def _window_from_mapping(candidate: Mapping[str, Any], fallback_name: str) -> dict[str, Any] | None:
    """Extract the small stable subset of a provider rate-limit window."""

    remaining_entry = _mapping_entry(
        candidate,
        "remaining_percent",
        "remaining_percentage",
        "remainingPercent",
        "remainingPercentage",
        "headroom_percent",
        "headroomPercent",
    )
    used_entry = _mapping_entry(
        candidate,
        "used_percent",
        "used_percentage",
        "usedPercent",
        "usedPercentage",
        "utilization",
        "utilisation",
        "utilization_percent",
        "utilisation_percent",
        "percent_used",
    )
    remaining = _number(remaining_entry[1], fraction_is_percent=False) if remaining_entry else None
    # Claude's bare ``utilization`` / ``utilisation`` fields are ratios. A
    # field explicitly named ``usedPercent`` (or another percent spelling) is
    # already a percentage, so a valid 1% value must not become 100%.
    used = (
        _number(
            used_entry[1],
            fraction_is_percent=used_entry[0] in {"utilization", "utilisation"},
        )
        if used_entry
        else None
    )
    if remaining is None and used is None:
        return None
    if remaining is None:
        remaining = max(0.0, 100.0 - used)
    if used is None:
        used = max(0.0, 100.0 - remaining)
    name = _mapping_value(candidate, "window", "window_name", "rate_limit_type", "limit_type", "name")
    reset = _mapping_value(candidate, "resets_at", "reset_at", "resetsAt", "resetAt", "reset")
    return {
        "window": bounded_text(name if name is not None else fallback_name, 80),
        "remaining_percent": round(remaining, 3),
        "used_percent": round(used, 3),
        "resets_at": bounded_text(reset, 128) if reset is not None else None,
    }


def extract_rate_limit_windows(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract rate-limit windows from common Claude JSONL event shapes.

    Claude's event schema has changed over time, so this accepts both a single
    ``rate_limit_info`` object and named nested windows.  It intentionally
    returns only percentages and reset times, never arbitrary provider payload.
    """

    roots: list[tuple[str, Any]] = []
    for key, value in event.items():
        normalised = _normalised_key(key)
        if normalised in {"ratelimitinfo", "ratelimit", "ratelimits", "usagewindow", "usagewindows"}:
            roots.append((str(key), value))
    if _normalised_key(event.get("type", "")) == "ratelimitevent":
        roots.append(("rate_limit_event", event))

    windows: list[dict[str, Any]] = []

    def visit(value: Any, fallback_name: str, depth: int) -> None:
        if depth > 5:
            return
        if isinstance(value, Mapping):
            extracted = _window_from_mapping(value, fallback_name)
            if extracted is not None:
                windows.append(extracted)
                return
            for key, nested in value.items():
                if isinstance(nested, (Mapping, list, tuple)):
                    visit(nested, str(key), depth + 1)
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                visit(nested, f"{fallback_name}-{index + 1}", depth + 1)

    for fallback_name, root in roots:
        visit(root, fallback_name, 0)

    # A provider may repeat the same window in a wrapper and an inner object.
    # Keep the most specific/latest representation while bounding the record.
    deduplicated: dict[str, dict[str, Any]] = {}
    for window in windows:
        deduplicated[window["window"]] = window
    return list(deduplicated.values())[:8]


def classify_flow_control(
    windows: Sequence[Mapping[str, Any]], *, warning_percent: float = 15.0, suspend_percent: float = 10.0
) -> dict[str, Any]:
    """Return the safe scheduling signal for a set of usage windows.

    ``SUSPENDED`` means do not start further work.  It does not itself kill a
    running worker; that policy belongs to the supervisor so it can checkpoint
    at a safe boundary.
    """

    if not 0 <= suspend_percent <= warning_percent <= 100:
        raise ValueError("usage thresholds must satisfy 0 <= suspend <= warning <= 100")
    candidates: list[tuple[float, Mapping[str, Any]]] = []
    for window in windows:
        remaining = _number(window.get("remaining_percent"), fraction_is_percent=False)
        if remaining is not None:
            candidates.append((remaining, window))
    if not candidates:
        return {
            "state": "OK",
            "action": "allow",
            "reason": "usage-unavailable",
            "remaining_percent": None,
            "window": None,
            "resets_at": None,
        }
    remaining, limiting_window = min(candidates, key=lambda item: item[0])
    if remaining <= suspend_percent:
        state, action = "SUSPENDED", "suspend"
    elif remaining <= warning_percent:
        state, action = "WARNING", "warn"
    else:
        state, action = "OK", "allow"
    return {
        "state": state,
        "action": action,
        "reason": "usage-headroom",
        "remaining_percent": round(remaining, 3),
        "window": bounded_text(limiting_window.get("window", "unknown"), 80),
        "resets_at": limiting_window.get("resets_at"),
    }


def _extract_session_id(event: Mapping[str, Any]) -> str | None:
    for source in (event, event.get("metadata"), event.get("session")):
        if not isinstance(source, Mapping):
            continue
        value = _mapping_value(source, "session_id", "sessionId", "uuid")
        if value not in (None, ""):
            return bounded_text(value, MAX_SESSION_ID_CHARS)
    return None


def _file_values(event: Mapping[str, Any]) -> list[str]:
    """Find explicitly labelled file arrays without serialising arbitrary events."""

    result: list[str] = []
    file_keys = {
        "changedfiles",
        "artifactchangedfiles",
        "productchangedfiles",
        "fileschanged",
        "modifiedfiles",
        "writtenfiles",
    }

    def visit(value: Any, depth: int) -> None:
        if depth > 4 or not isinstance(value, Mapping):
            return
        for key, nested in value.items():
            if _normalised_key(key) in file_keys and isinstance(nested, (list, tuple)):
                result.extend(str(item) for item in nested if isinstance(item, (str, Path)))
            elif isinstance(nested, Mapping):
                visit(nested, depth + 1)

    visit(event, 0)
    return result


def _event_text_summary(event: Mapping[str, Any]) -> str | None:
    for key in ("result", "summary", "message", "error", "errors"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return bounded_text(value, MAX_TEXT_SUMMARY_CHARS)
        if isinstance(value, list):
            strings = [entry for entry in value if isinstance(entry, str)]
            if strings:
                return bounded_text("; ".join(strings), MAX_TEXT_SUMMARY_CHARS)
    return None


def _terminal_outcome(event: Mapping[str, Any]) -> str | None:
    event_type = _normalised_key(event.get("type", ""))
    if event_type not in {"result", "terminal", "error"} and "terminal_reason" not in event:
        return None
    reason = _normalised_key(event.get("terminal_reason") or event.get("reason") or "")
    subtype = _normalised_key(event.get("subtype", ""))
    is_error = event.get("is_error") is True or event_type == "error"
    if reason in {"timeout", "timedout", "walltimeout"}:
        return "timeout"
    if reason in {"ratelimit", "usagelimit", "suspended"}:
        return "suspended"
    if is_error or subtype.startswith("error") or reason in {"maxturns", "cancelled", "canceled", "failed"}:
        return "failed"
    if reason in {"completed", "success", "endturn"} or subtype in {"success", "completed"} or event_type == "result":
        return "success"
    return "failed"


@dataclass(frozen=True)
class RelayResult:
    """The bounded result returned to a dispatcher or other controller."""

    returncode: int
    timed_out: bool
    stalled: bool
    stdout_summary: str
    stderr_summary: str
    status_path: str
    flow_control_path: str
    stream_path: str
    semantic_outcome: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClaudeRelay:
    """Parse a Claude stdout JSONL stream and publish compact durable state."""

    def __init__(
        self,
        run_dir: Path | str,
        *,
        warning_percent: float = 15.0,
        suspend_percent: float = 10.0,
        changed_file_sample_limit: int = DEFAULT_CHANGED_FILE_SAMPLE_LIMIT,
    ) -> None:
        if changed_file_sample_limit < 1:
            raise ValueError("changed_file_sample_limit must be positive")
        # Validate thresholds eagerly even before a rate-limit event arrives.
        classify_flow_control([], warning_percent=warning_percent, suspend_percent=suspend_percent)
        self.run_dir = Path(run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.stream_path = self.run_dir / STREAM_FILENAME
        self.status_path = self.run_dir / STATUS_FILENAME
        self.flow_control_path = self.run_dir / FLOW_CONTROL_FILENAME
        self.warning_percent = warning_percent
        self.suspend_percent = suspend_percent
        self.changed_file_sample_limit = changed_file_sample_limit
        stream_descriptor = os.open(
            self.stream_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        os.fchmod(stream_descriptor, 0o600)
        self._stream_handle = os.fdopen(stream_descriptor, "a", encoding="utf-8")
        now = utc_timestamp()
        self._windows: dict[str, dict[str, Any]] = {}
        self._changed_file_count = 0
        self._changed_file_sample: list[str] = []
        self._suspend_latched = False
        self._flow = self._new_flow(now)
        self._status: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "worker": "claude",
            "state": "running",
            "semantic_outcome": None,
            "started_at": now,
            "updated_at": now,
            "last_activity_at": None,
            "last_event_type": None,
            "session_id": None,
            "stream_path": self.stream_path.name,
            "event_counts": {"raw_lines": 0, "parsed_events": 0, "malformed_events": 0},
            "changed_files": {"count": 0, "sample": [], "truncated": False},
            "rate_limit": {"windows": [], "minimum_remaining_percent": None},
            "terminal": None,
        }
        self._persist()

    def __enter__(self) -> "ClaudeRelay":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._stream_handle.closed:
            self._stream_handle.flush()
            self._stream_handle.close()

    def _new_flow(self, now: str) -> dict[str, Any]:
        flow = classify_flow_control(
            [], warning_percent=self.warning_percent, suspend_percent=self.suspend_percent
        )
        return {"schema_version": SCHEMA_VERSION, "updated_at": now, **flow}

    def _persist(self) -> None:
        self._status["updated_at"] = utc_timestamp()
        self._status["changed_files"] = {
            "count": self._changed_file_count,
            "sample": list(self._changed_file_sample),
            "truncated": self._changed_file_count > len(self._changed_file_sample),
        }
        windows = list(self._windows.values())[:8]
        remaining = [window["remaining_percent"] for window in windows if window.get("remaining_percent") is not None]
        self._status["rate_limit"] = {
            "windows": windows,
            "minimum_remaining_percent": min(remaining) if remaining else None,
        }
        atomic_write_json(self.status_path, self._status)
        atomic_write_json(self.flow_control_path, self._flow)

    def _append_raw_line(self, line: str) -> None:
        self._stream_handle.write(line if line.endswith("\n") else line + "\n")
        self._stream_handle.flush()

    def consume_line(self, line: str) -> bool:
        """Append one raw stdout line and return whether it parsed as a JSON object."""

        self._append_raw_line(line)
        self._status["event_counts"]["raw_lines"] += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._status["event_counts"]["malformed_events"] += 1
            self._persist()
            return False
        if not isinstance(event, Mapping):
            self._status["event_counts"]["malformed_events"] += 1
            self._persist()
            return False
        self.consume_event(event)
        return True

    def consume_event(self, event: Mapping[str, Any]) -> None:
        """Record a parsed event.  Use :meth:`consume_line` for raw JSONL input."""

        now = utc_timestamp()
        self._status["event_counts"]["parsed_events"] += 1
        self._status["last_activity_at"] = now
        event_type = bounded_text(event.get("type", "unknown"), MAX_EVENT_TYPE_CHARS)
        self._status["last_event_type"] = event_type
        session_id = _extract_session_id(event)
        if session_id:
            self._status["session_id"] = session_id
        for file_path in _file_values(event):
            self._changed_file_count += 1
            if len(self._changed_file_sample) < self.changed_file_sample_limit:
                self._changed_file_sample.append(bounded_text(file_path, MAX_FILE_PATH_CHARS))
        windows = extract_rate_limit_windows(event)
        if windows:
            for window in windows:
                self._windows[window["window"]] = window
            flow = classify_flow_control(
                list(self._windows.values()),
                warning_percent=self.warning_percent,
                suspend_percent=self.suspend_percent,
            )
            # A suspension is deliberately sticky.  A separate supervisor must
            # perform the fresh reset check and clear/restart a later worker.
            if flow["state"] == "SUSPENDED":
                self._suspend_latched = True
            if self._suspend_latched:
                flow["state"] = "SUSPENDED"
                flow["action"] = "suspend"
                flow["reason"] = "usage-headroom"
            self._flow = {"schema_version": SCHEMA_VERSION, "updated_at": now, **flow}
        terminal_outcome = _terminal_outcome(event)
        if terminal_outcome is not None:
            self._status["semantic_outcome"] = terminal_outcome
            self._status["state"] = {
                "success": "completed",
                "failed": "failed",
                "timeout": "timed_out",
                "suspended": "suspended",
            }[terminal_outcome]
            self._status["terminal"] = {
                "reason": bounded_text(event.get("terminal_reason") or event.get("reason") or "unknown", 128),
                "subtype": bounded_text(event.get("subtype") or "", 128) or None,
                "is_error": event.get("is_error") is True,
                "summary": _event_text_summary(event),
            }
        self._persist()

    def finalize(
        self,
        *,
        returncode: int,
        timed_out: bool,
        stalled: bool = False,
        stderr_summary: str = "",
    ) -> str:
        """Close the worker lifecycle and return its semantic outcome."""

        if timed_out:
            outcome, state = "timeout", "timed_out"
            terminal = {"reason": "wall_timeout", "subtype": None, "is_error": True, "summary": None}
        elif stalled:
            outcome, state = "stalled", "stalled"
            terminal = {"reason": "inactivity_timeout", "subtype": None, "is_error": True, "summary": None}
        elif self._status["semantic_outcome"] is not None:
            outcome = str(self._status["semantic_outcome"])
            state = str(self._status["state"])
            terminal = self._status["terminal"]
        elif returncode == 0:
            outcome, state = "success", "completed"
            terminal = {"reason": "process_exit", "subtype": None, "is_error": False, "summary": None}
        else:
            outcome, state = "failed", "failed"
            terminal = {
                "reason": "process_exit",
                "subtype": None,
                "is_error": True,
                "summary": bounded_text(stderr_summary, MAX_TEXT_SUMMARY_CHARS) if stderr_summary else None,
            }
        self._status["semantic_outcome"] = outcome
        self._status["state"] = state
        self._status["terminal"] = terminal
        self._persist()
        self.close()
        return outcome

    def caller_summary(self) -> str:
        """Return valid, deliberately small JSON suitable for a parent process."""

        terminal = self._status.get("terminal") or {}
        payload: dict[str, Any] = {
            "changed_file_count": self._changed_file_count,
            "changed_file_sample": list(self._changed_file_sample),
            "event_counts": self._status["event_counts"],
            "flow_control": self._flow["state"],
            "last_event_type": self._status["last_event_type"],
            "semantic_outcome": self._status["semantic_outcome"],
            "session_id": self._status["session_id"],
            "state": self._status["state"],
            "terminal_reason": terminal.get("reason"),
            "terminal_summary": terminal.get("summary"),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        while len(encoded) > MAX_CALLER_SUMMARY_CHARS and payload["changed_file_sample"]:
            payload["changed_file_sample"].pop()
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded) > MAX_CALLER_SUMMARY_CHARS:
            payload["terminal_summary"] = None
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded) > MAX_CALLER_SUMMARY_CHARS:
            encoded = json.dumps(
                {
                    "changed_file_count": self._changed_file_count,
                    "flow_control": self._flow["state"],
                    "semantic_outcome": self._status["semantic_outcome"],
                    "summary_truncated": True,
                },
                separators=(",", ":"),
            )
        return encoded


class _BoundedTail:
    """Keep the final part of stderr without retaining an unbounded process log."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._text = ""
        self._lock = threading.Lock()

    def append(self, text: str) -> None:
        with self._lock:
            combined = self._text + text
            if len(combined) <= self.limit:
                self._text = combined
            elif self.limit == 1:
                self._text = "…"
            else:
                self._text = "…" + combined[-(self.limit - 1) :]

    def value(self) -> str:
        with self._lock:
            return self._text


def run(
    command: Sequence[str],
    *,
    cwd: Path | str,
    run_dir: Path | str,
    timeout_seconds: float | None,
    stall_timeout_seconds: float | None = None,
    environment: Mapping[str, str] | None = None,
) -> RelayResult:
    """Run a Claude JSONL command while retaining only bounded caller output.

    ``command`` must already select Claude's stream/JSONL output format. This
    function neither constructs a Claude command nor invokes it during module
    import. Workflow dispatches pass no wall or inactivity limit; liveness is
    reported by the controller without terminating the worker.
    """

    if not command:
        raise ValueError("command must not be empty")
    if stall_timeout_seconds is not None and stall_timeout_seconds <= 0:
        raise ValueError("stall_timeout_seconds must be positive when supplied")
    relay = ClaudeRelay(run_dir)
    stderr_tail = _BoundedTail(MAX_STDERR_SUMMARY_CHARS)
    process: subprocess.Popen[str] | None = None
    timed_out = False
    stalled = False
    returncode = 127
    try:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(environment) if environment is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        activity_lock = threading.Lock()
        last_activity_monotonic = time.monotonic()

        def note_activity() -> None:
            nonlocal last_activity_monotonic
            with activity_lock:
                last_activity_monotonic = time.monotonic()

        def inactivity_expired() -> bool:
            if stall_timeout_seconds is None:
                return False
            with activity_lock:
                return time.monotonic() - last_activity_monotonic >= stall_timeout_seconds

        def read_stdout() -> None:
            for line in process.stdout:
                note_activity()
                relay.consume_line(line)

        def read_stderr() -> None:
            while True:
                chunk = process.stderr.read(1024)
                if not chunk:
                    return
                note_activity()
                stderr_tail.append(chunk)

        stdout_thread = threading.Thread(target=read_stdout, name="claude-relay-stdout", daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, name="claude-relay-stderr", daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        started = time.monotonic()
        while process.poll() is None:
            if wall_timeout_expired(started, timeout_seconds):
                timed_out = True
                # The CLI may have spawned helpers.  It owns a dedicated
                # process group, so do not leave them consuming quota after a
                # relay wall timeout.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                break
            if inactivity_expired():
                stalled = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                break
            time.sleep(0.05)
        returncode = process.wait()
        # The child has exited and closed both pipes.  Join fully so the final
        # status includes every event already emitted before we classify it.
        stdout_thread.join()
        stderr_thread.join()
    except OSError as error:
        stderr_tail.append(str(error))
        returncode = 127
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            returncode = process.wait()
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
        outcome = relay.finalize(
            returncode=returncode,
            timed_out=timed_out,
            stalled=stalled,
            stderr_summary=stderr_tail.value(),
        )
    return RelayResult(
        returncode=returncode,
        timed_out=timed_out,
        stalled=stalled,
        stdout_summary=relay.caller_summary(),
        stderr_summary=stderr_tail.value(),
        status_path=str(relay.status_path),
        flow_control_path=str(relay.flow_control_path),
        stream_path=str(relay.stream_path),
        semantic_outcome=outcome,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Small optional CLI for manually relaying a command after ``--``."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--stall-timeout-seconds", type=float, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv)
    command = arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
    result = run(
        command,
        cwd=arguments.cwd,
        run_dir=arguments.run_dir,
        timeout_seconds=arguments.timeout_seconds,
        stall_timeout_seconds=arguments.stall_timeout_seconds,
    )
    print(json.dumps(result.as_dict(), sort_keys=True))
    return 0 if result.semantic_outcome == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
