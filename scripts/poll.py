#!/usr/bin/env python3
"""Read durable workflow-dispatch state without waiting on a terminal call."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import sys
import time


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def optional_json(path_value: object) -> dict | None:
    """Read a bounded sidecar when it exists without making polling fragile."""

    if not isinstance(path_value, str):
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def liveness(worker: dict | None, submitted_at_epoch: object, *, now_epoch: float | None = None) -> dict:
    """Classify silence for reporting only; never interrupt the worker."""

    observed = time.time() if now_epoch is None else now_epoch
    timestamp = None
    source = None
    if worker:
        for field in ("last_activity_at", "started_at"):
            value = worker.get(field)
            if isinstance(value, str):
                try:
                    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
                    source = field
                    break
                except ValueError:
                    pass
    if timestamp is None and isinstance(submitted_at_epoch, (int, float)) and not isinstance(submitted_at_epoch, bool):
        timestamp = float(submitted_at_epoch)
        source = "submitted_at_epoch"
    if timestamp is None:
        return {"state": "UNKNOWN", "silent_seconds": None, "source": None}
    silent_seconds = max(0, int(observed - timestamp))
    state = "STALLED_SUSPECTED" if silent_seconds >= 1800 else "QUIET" if silent_seconds >= 900 else "ACTIVE"
    return {"state": state, "silent_seconds": silent_seconds, "source": source}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise ValueError("usage: poll.py <job-dir>")
    job_dir = Path(argv[1]).resolve()
    metadata = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    resume = metadata.get("resume") if isinstance(metadata.get("resume"), dict) else None
    resume_state = optional_json(str(job_dir / "resume-state.json"))
    envelope = Path(metadata["envelope_path"])
    worker = optional_json(metadata.get("worker_status_path"))
    flow_control = optional_json(metadata.get("flow_control_path"))
    worker_liveness = liveness(worker, metadata.get("submitted_at_epoch"))
    if envelope.is_file():
        result = json.loads(envelope.read_text(encoding="utf-8"))
        outcome = result.get("outcome") if isinstance(result, dict) else None
        terminal_status = {
            "success": "completed",
            "suspended": "suspended",
            "timeout": "timeout",
            "stalled": "stalled",
            "scope-violation": "scope-violation",
            "failed": "failed",
        }
        status = terminal_status.get(outcome, "failed")
        print(
            json.dumps(
                {
                    "status": status,
                    "result": result,
                    "worker": worker,
                    "flow_control": flow_control,
                    "liveness": {"state": "NOT_APPLICABLE", "silent_seconds": None, "source": None},
                    "resume": resume,
                    "resume_state": resume_state,
                },
                sort_keys=True,
            )
        )
        return 0
    pid_value = metadata.get("pid")
    if not isinstance(pid_value, int) or isinstance(pid_value, bool) or pid_value <= 0:
        status = "submitting" if metadata.get("state") == "submitting" else "failed-submit"
        print(
            json.dumps(
                {
                    "status": status,
                    "pid": None,
                    "job_dir": str(job_dir),
                    "worker": worker,
                    "flow_control": flow_control,
                    "liveness": worker_liveness,
                    "resume": resume,
                    "resume_state": resume_state,
                },
                sort_keys=True,
            )
        )
        return 0
    alive = process_alive(pid_value)
    flow_state = flow_control.get("state") if flow_control else None
    if alive:
        status = "draining" if flow_state == "SUSPENDED" else "running"
    elif flow_state == "SUSPENDED":
        status = "suspended"
    elif flow_state == "BLOCKED":
        status = "blocked"
    else:
        status = "failed-no-envelope"
    print(
        json.dumps(
            {
                "status": status,
                "pid": pid_value,
                "job_dir": str(job_dir),
                "worker": worker,
                "flow_control": flow_control,
                "liveness": worker_liveness,
                "resume": resume,
                "resume_state": resume_state,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid-job", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
