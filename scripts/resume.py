#!/usr/bin/env python3
"""Resume one suspended external-Claude dispatch at a verified reset boundary.

This helper intentionally performs no waiting, polling, provider calls, or
native-Codex resume.  A workflow heartbeat or human invokes it only after the
saved Claude flow-control record says its reset is due.  The new durable job
uses Claude's saved session ID and keeps explicit parent/child provenance.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1


class ResumeError(ValueError):
    """A checkpoint is not safe to resume automatically."""


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically persist compact local resume state."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
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
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResumeError(f"cannot read {description}: {error}") from error
    if not isinstance(value, dict):
        raise ResumeError(f"{description} must be a JSON object")
    return value


def parse_reset_epoch(value: object) -> int:
    """Accept the bounded reset values emitted by the relay, never guessing."""

    if isinstance(value, bool) or value is None:
        raise ResumeError("suspended Claude flow has no reset time")
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0:
            raise ResumeError("suspended Claude reset time must be a finite non-negative value")
        return int(numeric / 1000 if numeric >= 100_000_000_000 else numeric)
    if not isinstance(value, str) or not value.strip():
        raise ResumeError("suspended Claude reset time is invalid")
    text = value.strip()
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        if not math.isfinite(numeric) or numeric < 0:
            raise ResumeError("suspended Claude reset time must be a finite non-negative value")
        return int(numeric / 1000 if numeric >= 100_000_000_000 else numeric)
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ResumeError("suspended Claude reset time is not ISO-8601 or Unix time") from error
    if timestamp.tzinfo is None:
        raise ResumeError("suspended Claude reset time must include a timezone")
    return int(timestamp.astimezone(timezone.utc).timestamp())


def parse_now_epoch(value: int | float | None) -> int:
    """Validate the injectable clock rather than treating NaN as a reset."""

    numeric = time.time() if value is None else float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ResumeError("current time must be a finite non-negative Unix timestamp")
    return int(numeric)


def _non_empty_string(value: object, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResumeError(f"{description} must be a non-empty string")
    return value.strip()


def suspended_claude_checkpoint(parent_job_dir: Path) -> tuple[dict[str, Any], dict[str, Any], str, int]:
    """Return the original metadata, envelope, session ID, and due epoch."""

    metadata = read_json_object(parent_job_dir / "job.json", "parent job metadata")
    if metadata.get("target") != "claude-cli":
        raise ResumeError("only a suspended claude-cli job can be resumed here")
    envelope_path = Path(_non_empty_string(metadata.get("envelope_path"), "parent envelope path"))
    envelope = read_json_object(envelope_path, "parent result envelope")
    if envelope.get("outcome") != "suspended":
        raise ResumeError("parent job is not suspended")
    worker = envelope.get("worker")
    if not isinstance(worker, dict) or worker.get("kind") != "external-claude-worker":
        raise ResumeError("parent job has no resumable external Claude worker")
    summary = worker.get("summary")
    flow = worker.get("flow_control")
    if not isinstance(summary, dict) or not isinstance(flow, dict):
        raise ResumeError("parent job has incomplete worker checkpoint state")
    session_id = _non_empty_string(summary.get("session_id"), "Claude session ID")
    if flow.get("state") != "SUSPENDED":
        raise ResumeError("parent Claude flow-control record is not suspended")
    reset_epoch = parse_reset_epoch(flow.get("resets_at"))
    return metadata, envelope, session_id, reset_epoch


def next_child_job_dir(parent_job_dir: Path) -> tuple[Path, int]:
    """Select a never-reused durable child directory without pre-creating it."""

    resume_root = parent_job_dir / "resumes"
    resume_root.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while (resume_root / f"resume-{attempt:03d}").exists():
        attempt += 1
    return resume_root / f"resume-{attempt:03d}", attempt


def acquire_lock(parent_job_dir: Path) -> Path:
    """Avoid two heartbeats launching the same saved Claude session at once."""

    state_path = parent_job_dir / "resume-state.json"
    if state_path.exists():
        state = read_json_object(state_path, "existing resume state")
        child = state.get("child_job_dir", "an existing child job")
        if state.get("state") == "submitted":
            raise ResumeError(f"resume already submitted to {child}")
        raise ResumeError(
            f"a prior resume attempt is recorded as {state.get('state', 'unknown')} for {child}; "
            "manual reconciliation is required before retrying"
        )
    lock = parent_job_dir / ".resume.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ResumeError("a resume attempt is already in progress; inspect .resume.lock") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"created_at_epoch": time.time()}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return lock


def release_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def run_submit(
    *,
    submit_script: Path,
    metadata: Mapping[str, Any],
    child_job_dir: Path,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Launch the existing durable-submission path and validate its compact reply."""

    command = [
        sys.executable,
        str(submit_script),
        _non_empty_string(metadata.get("target"), "parent target"),
        _non_empty_string(metadata.get("label"), "parent label"),
        _non_empty_string(metadata.get("mode"), "parent mode"),
        _non_empty_string(metadata.get("prompt_file"), "parent prompt file"),
        _non_empty_string(metadata.get("artifact_root"), "parent artifact root"),
        _non_empty_string(metadata.get("product_root"), "parent product root"),
        str(child_job_dir),
    ]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, env=dict(environment), timeout=30
        )
    except subprocess.TimeoutExpired as error:
        raise ResumeError("resume submission did not return within 30 seconds") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-600:] or completed.stdout.strip()[-600:] or "no diagnostic output"
        raise ResumeError(f"resume submission failed: {detail}")
    try:
        reply = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ResumeError("resume submission did not return JSON") from error
    if not isinstance(reply, dict) or reply.get("status") != "submitted":
        raise ResumeError("resume submission did not confirm a durable job")
    returned_job_dir = Path(_non_empty_string(reply.get("job_dir"), "submitted job directory")).resolve()
    if returned_job_dir != child_job_dir.resolve():
        raise ResumeError("resume submission returned an unexpected child job directory")
    if not child_job_dir.is_dir():
        raise ResumeError("resume submission did not create its child job directory")
    return reply


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent_job_dir", help="suspended claude-cli job directory")
    parser.add_argument("--now-epoch", type=float, help="override clock for deterministic checks")
    parser.add_argument(
        "--submit-script",
        default=str(ROOT / "scripts" / "submit.py"),
        help="submission helper (defaults to this workflow's submit.py)",
    )
    args = parser.parse_args(argv)
    parent_job_dir = Path(args.parent_job_dir).resolve()
    try:
        metadata, _envelope, session_id, reset_epoch = suspended_claude_checkpoint(parent_job_dir)
        now_epoch = parse_now_epoch(args.now_epoch)
        if now_epoch < reset_epoch:
            raise ResumeError(f"Claude reset is not due until {reset_epoch}")
        lock = acquire_lock(parent_job_dir)
    except (OSError, ResumeError) as error:
        print(json.dumps({"status": "not-resumed", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2

    try:
        child_job_dir, attempt = next_child_job_dir(parent_job_dir)
        provenance_path = child_job_dir / "resume-provenance.json"
        provenance = {
            "schema_version": SCHEMA_VERSION,
            "parent_job_dir": str(parent_job_dir),
            "parent_envelope_path": str(metadata["envelope_path"]),
            "child_job_dir": str(child_job_dir),
            "session_id": session_id,
            "reset_due_epoch": reset_epoch,
            "resumed_at_epoch": now_epoch,
            "attempt": attempt,
        }
        # Persist intent before the process that can create a child starts. If
        # anything after this point is ambiguous, later heartbeats fail closed
        # rather than submit the same Claude session a second time.
        atomic_write_json(
            parent_job_dir / "resume-state.json",
            {"state": "submitting", **provenance},
        )
        environment = dict(os.environ)
        environment.update(
            {
                "WORKFLOW_CLAUDE_RESUME_SESSION": session_id,
                "WORKFLOW_RESUME_PARENT_JOB_DIR": str(parent_job_dir),
                "WORKFLOW_RESUME_PARENT_ENVELOPE_PATH": str(metadata["envelope_path"]),
                "WORKFLOW_RESUME_PROVENANCE_PATH": str(provenance_path),
                "WORKFLOW_RESUME_ATTEMPT": str(attempt),
            }
        )
        reply = run_submit(
            submit_script=Path(args.submit_script).resolve(),
            metadata=metadata,
            child_job_dir=child_job_dir,
            environment=environment,
        )
        atomic_write_json(provenance_path, provenance)
        atomic_write_json(
            parent_job_dir / "resume-state.json",
            {"schema_version": SCHEMA_VERSION, "state": "submitted", **provenance},
        )
        print(
            json.dumps(
                {
                    "status": "resumed",
                    "parent_job_dir": str(parent_job_dir),
                    "child_job_dir": str(child_job_dir),
                    "session_id": session_id,
                    "reset_due_epoch": reset_epoch,
                    "resume_provenance_path": str(provenance_path),
                    "submission": reply,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ResumeError) as error:
        print(json.dumps({"status": "not-resumed", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    finally:
        release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
