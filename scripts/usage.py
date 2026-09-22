#!/usr/bin/env python3
"""Read subscription usage windows for the Claude and Codex targets and decide whether to suspend.

Windows are normalised to {"five_hour": {"used": 0..1, "resets_at": epoch}, "seven_day": {...}}.
Codex is read through the app-server `account/rateLimits/read` call (no model call). Claude only reports usage on
`rate_limit_event` stream events, so a cheap probe run refreshes it when the cache is stale.
Usage:  usage.py <target-id> [--refresh]
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

from mini_toml import load

SHARED_ROOT = Path(__file__).resolve().parents[1]
RULES = SHARED_ROOT / "targets" / "stage-assignment-rules.toml"
WINDOW_BY_MINUTES = {300: "five_hour", 10080: "seven_day"}


def state_dir() -> Path:
    return Path(os.environ.get("WORKFLOW_STATE_DIR", SHARED_ROOT / "state"))


def policy() -> dict:
    """Monitoring and usage policy from the shared rules file, with environment overrides for tests and one-off runs."""
    rules = load(RULES)
    merged = {**rules.get("monitoring", {}), **rules.get("usage", {})}
    overrides = {
        "WORKFLOW_IDLE_TIMEOUT_SECONDS": ("idle_timeout_seconds", int),
        "WORKFLOW_DISPATCH_TIMEOUT_SECONDS": ("max_wall_seconds", int),
        "WORKFLOW_USAGE_HEADROOM": ("suspend_when_headroom_below", float),
        "WORKFLOW_RESUME_BUFFER_SECONDS": ("resume_buffer_seconds", int),
        "WORKFLOW_USAGE_POLL_SECONDS": ("usage_poll_seconds", int),
    }
    for name, (key, cast) in overrides.items():
        if os.environ.get(name):
            merged[key] = cast(os.environ[name])
    return merged


def mock_usage(engine: str) -> dict | None:
    path = os.environ.get("WORKFLOW_USAGE_MOCK_FILE")
    if path and os.environ.get("WORKFLOW_DISPATCH_ALLOW_MOCK") == "1" and Path(path).is_file():
        return json.loads(Path(path).read_text(encoding="utf-8")).get(engine)
    return None


def windows_from_claude_event(event: dict) -> dict:
    info = event.get("rate_limit_info", {})
    windows = {}
    for name, window in info.get("unifiedWindows", {}).items():
        windows[name] = {"used": float(window["utilization"]), "resets_at": window.get("resetsAt")}
    if not windows and info.get("rateLimitType"):
        windows[info["rateLimitType"]] = {"used": 1.0 if info.get("status") != "allowed" else 0.0, "resets_at": info.get("resetsAt")}
    return windows


def find_binary(name: str, target_file: str, env_var: str | None = None) -> str | None:
    """PATH first, then an explicit env var, then the install locations recorded in the target registry."""
    import shutil
    candidates = [os.environ.get(env_var)] if env_var else []
    candidates += load(SHARED_ROOT / "targets" / target_file).get("binary_paths", [])
    return shutil.which(name) or next((path for path in candidates if path and Path(path).is_file()), None)


def codex_binary() -> str | None:
    return find_binary("codex", "codex.toml", "CODEX_CLI_PATH")


def read_codex_windows(timeout: int = 25) -> dict | None:
    binary = codex_binary()
    if not binary:
        return None
    process = subprocess.Popen([binary, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def send(message: dict) -> None:
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def reply(wanted: int) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 1)
            if not ready:
                continue
            line = process.stdout.readline()
            if not line:
                return None
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") == wanted:
                return message
        return None

    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "workflow-usage", "version": "1"}}})
        if not reply(1):
            return None
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read", "params": None})
        message = reply(2)
    finally:
        process.terminate()
    limits = ((message or {}).get("result") or {}).get("rateLimits")
    if not limits:
        return None
    windows = {}
    for key in ("primary", "secondary"):
        window = limits.get(key)
        if window:
            name = WINDOW_BY_MINUTES.get(window.get("windowDurationMins"), "five_hour" if key == "primary" else "seven_day")
            windows[name] = {"used": window["usedPercent"] / 100.0, "resets_at": window.get("resetsAt")}
    return windows


def probe_claude_windows(timeout: int = 90) -> dict | None:
    """One-turn haiku run whose stream carries a rate_limit_event. Costs a fraction of a cent of quota."""
    binary = find_binary("claude", "claude-cli.toml")
    if not binary:
        return None
    try:
        completed = subprocess.run(
            [binary, "-p", "--model", "haiku", "--output-format", "stream-json", "--verbose", "--max-turns", "1",
             "--permission-mode", "default", "--settings", '{"permissions":{"allow":[]}}'],
            input="Reply with ok.", capture_output=True, text=True, timeout=timeout, check=False, cwd="/tmp")
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "rate_limit_event":
                return windows_from_claude_event(event)
    return None


def cache_path() -> Path:
    return state_dir() / "usage.json"


def load_cache() -> dict:
    try:
        return json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record(engine: str, windows: dict) -> None:
    cache = load_cache()
    cache[engine] = {"observed_at": time.time(), "windows": windows}
    cache_path().parent.mkdir(parents=True, exist_ok=True)
    cache_path().write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def current(engine: str, refresh: bool = False) -> dict | None:
    """Latest known windows for an engine ("claude-code" or "codex-cli"); None when unknown."""
    mocked = mock_usage(engine)
    if mocked is not None:
        return mocked
    cached = load_cache().get(engine)
    if cached and not refresh and time.time() - cached["observed_at"] < policy()["usage_cache_seconds"]:
        return cached["windows"]
    windows = read_codex_windows() if engine == "codex-cli" else probe_claude_windows() if engine == "claude-code" else None
    if windows:
        record(engine, windows)
        return windows
    return cached["windows"] if cached else None


def decide(windows: dict | None, now: float | None = None) -> dict:
    """Return {"action": "ok"|"suspend"|"blocked", "resets_at": epoch|None, "window": name|None, "used": float|None}."""
    if not windows:
        return {"action": "ok", "resets_at": None, "window": None, "used": None, "note": "usage unknown"}
    rules = policy()
    now = now or time.time()
    limit = 1.0 - float(rules["suspend_when_headroom_below"])
    for name in rules.get("blocking_windows", []):
        window = windows.get(name)
        if window and window["used"] >= limit and (window.get("resets_at") or 0) > now:
            return {"action": "blocked", "resets_at": window.get("resets_at"), "window": name, "used": window["used"]}
    for name in rules.get("guarded_windows", []):
        window = windows.get(name)
        if window and window["used"] >= limit and (window.get("resets_at") or 0) > now:
            return {"action": "suspend", "resets_at": window.get("resets_at"), "window": name, "used": window["used"]}
    return {"action": "ok", "resets_at": None, "window": None, "used": None}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: usage.py <claude-cli|codex|engine id> [--refresh]", file=sys.stderr)
        return 2
    engine = {"claude-cli": "claude-code", "codex": "codex-cli"}.get(argv[1], argv[1])
    windows = current(engine, refresh="--refresh" in argv)
    print(json.dumps({"engine": engine, "windows": windows, "decision": decide(windows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
