#!/usr/bin/env python3
"""Submit a workflow dispatch as a durable background job."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def resume_metadata_from_environment(environment: dict[str, str]) -> dict[str, str] | None:
    """Preserve bounded resume provenance supplied by ``resume.py``.

    The background child inherits these values before its first dispatch event.
    Recording them in ``job.json`` makes a resumed Claude session distinguishable
    from a fresh job without exposing a caller's full environment.
    """

    fields = {
        "parent_job_dir": "WORKFLOW_RESUME_PARENT_JOB_DIR",
        "parent_envelope_path": "WORKFLOW_RESUME_PARENT_ENVELOPE_PATH",
        "provenance_path": "WORKFLOW_RESUME_PROVENANCE_PATH",
        "attempt": "WORKFLOW_RESUME_ATTEMPT",
    }
    result = {
        field: environment[name]
        for field, name in fields.items()
        if isinstance(environment.get(name), str) and environment[name]
    }
    return result or None


def atomic_write_json(path: Path, value: dict) -> None:
    """Atomically publish durable job metadata with owner-only permissions."""

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
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


def open_private_log(path: Path):
    """Open an owner-only runner log without relying on the caller's umask."""

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 8:
        raise ValueError(
            "usage: submit.py <target> <label> <mode> <prompt-file> <artifact-root> <product-root> <job-dir>"
        )
    target, label, mode, prompt, artifact_root, product_root, job_dir_value = argv[1:]
    job_dir = Path(job_dir_value).resolve()
    if job_dir.exists():
        raise ValueError(f"job directory already exists: {job_dir}")
    job_dir.mkdir(parents=True, mode=0o700)
    job_dir.chmod(0o700)
    stdout_path = job_dir / "runner.stdout.log"
    stderr_path = job_dir / "runner.stderr.log"
    envelope_path = job_dir / "result-envelope.json"
    worker_status_path = job_dir / "worker-status.json"
    flow_control_path = job_dir / "flow-control.json"
    worker_stream_path = job_dir / "claude-events.jsonl"
    changed_file_audit_path = job_dir / "changed-files.json"
    command = [
        "bash", str(ROOT / "scripts" / "dispatch.sh"), target, label, mode,
        prompt, artifact_root, product_root,
    ]
    environment = os.environ.copy()
    environment["WORKFLOW_JOB_DIR"] = str(job_dir)
    environment["WORKFLOW_DISPATCH_ENVELOPE_PATH"] = str(envelope_path)
    metadata = {
        "pid": None,
        "state": "submitting",
        "submitted_at_epoch": time.time(),
        "target": target,
        "label": label,
        "mode": mode,
        "prompt_file": prompt,
        "artifact_root": artifact_root,
        "product_root": product_root,
        "envelope_path": str(envelope_path),
        "worker_status_path": str(worker_status_path),
        "flow_control_path": str(flow_control_path),
        "worker_stream_path": str(worker_stream_path),
        "changed_file_audit_path": str(changed_file_audit_path),
    }
    resume = resume_metadata_from_environment(environment)
    if resume is not None:
        metadata["resume"] = resume
    job_metadata_path = job_dir / "job.json"
    atomic_write_json(job_metadata_path, metadata)
    try:
        with open_private_log(stdout_path) as stdout, open_private_log(stderr_path) as stderr:
            process = subprocess.Popen(
                command,
                cwd=job_dir,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                env=environment,
            )
    except OSError as error:
        metadata["state"] = "submission_failed"
        metadata["submission_error"] = str(error)[-600:]
        atomic_write_json(job_metadata_path, metadata)
        raise
    metadata["pid"] = process.pid
    metadata["state"] = "running"
    atomic_write_json(job_metadata_path, metadata)
    print(
        json.dumps(
            {
                "status": "submitted",
                "job_dir": str(job_dir),
                "pid": process.pid,
                "worker_status_path": str(worker_status_path),
                "flow_control_path": str(flow_control_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "invalid-submit", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
