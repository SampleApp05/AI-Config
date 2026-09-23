#!/usr/bin/env python3
"""Run a registered workflow target with strict, audited write scope."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from claude_relay import run as run_claude_relay


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGED_FILE_SAMPLE_LIMIT = 50
MAX_CHANGED_FILE_SAMPLE_LIMIT = 100
MAX_CHANGED_FILE_PATH_CHARS = 240


def read_target(target_id: str) -> dict:
    path = ROOT / "targets" / f"{target_id}.toml"
    if not path.is_file():
        raise ValueError(f"unknown target: {target_id}")
    text = path.read_text(encoding="utf-8")

    def value(name: str) -> str:
        match = re.search(rf'^\s*{re.escape(name)}\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
        if not match:
            raise ValueError(f"target is missing {name}: {path}")
        return match.group(1)

    def integer(name: str) -> int:
        match = re.search(rf'^\s*{re.escape(name)}\s*=\s*(\d+)\s*$', text, re.MULTILINE)
        if not match:
            raise ValueError(f"target is missing {name}: {path}")
        return int(match.group(1))

    return {
        "id": value("id"),
        "engine": value("engine"),
        "label_prefix": value("label_prefix"),
        "hard_limits": {"max_prompt_chars": integer("max_prompt_chars")},
    }


def snapshot(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def changed(before: dict[str, str], after: dict[str, str]) -> set[str]:
    return {path for path in before | after if before.get(path) != after.get(path)}


def allowed_paths(prompt: str, mode: str) -> tuple[set[str], set[str]]:
    allowed = set(re.findall(r"^WORKFLOW_ALLOWED_PATH=(.+)$", prompt, re.MULTILINE))
    directories = set(re.findall(r"^WORKFLOW_ALLOWED_DIRECTORY=(.+)$", prompt, re.MULTILINE))
    artifacts = re.findall(r"^WORKFLOW_ARTIFACT_PATH=(.+)$", prompt, re.MULTILINE)
    if mode == "artifact":
        if len(artifacts) != 1:
            raise ValueError("artifact mode requires exactly one WORKFLOW_ARTIFACT_PATH marker")
        allowed.add(artifacts[0])
    if not allowed and not directories:
        raise ValueError("dispatch requires at least one scope marker")
    for value in allowed | directories:
        candidate = Path(value)
        if not value or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("scope markers must be non-empty repository-relative paths")
    normalized_directories = {value.rstrip("/") for value in directories}
    if "" in normalized_directories:
        raise ValueError("directory scope markers must not name the repository root")
    return allowed, normalized_directories


def path_is_allowed(path: str, files: set[str], directories: set[str]) -> bool:
    return path in files or any(path.startswith(f"{directory}/") for directory in directories)


def bounded_file_list(paths: set[str] | list[str], *, limit: int) -> tuple[list[str], bool]:
    """Return a stable, bounded sample suitable for a controller envelope."""

    if limit < 1 or limit > MAX_CHANGED_FILE_SAMPLE_LIMIT:
        raise ValueError(
            f"changed-file sample limit must be between 1 and {MAX_CHANGED_FILE_SAMPLE_LIMIT}"
        )
    def bounded_path(path: str) -> str:
        if len(path) <= MAX_CHANGED_FILE_PATH_CHARS:
            return path
        return path[: MAX_CHANGED_FILE_PATH_CHARS - 1] + "…"

    ordered = sorted(paths)
    return [bounded_path(path) for path in ordered[:limit]], len(ordered) > limit


def dispatch_run_dir() -> Path:
    """Locate a durable job directory or create a safe local spool directory.

    ``submit.py`` provides ``WORKFLOW_JOB_DIR``. Direct dispatches still need
    stream and audit sidecars, so they receive a private directory beneath an
    explicitly bounded temporary spool root instead of putting raw output on
    stdout.
    """

    value = os.environ.get("WORKFLOW_JOB_DIR")
    if value:
        directory = Path(value).resolve()
        if not directory.is_dir():
            raise ValueError("WORKFLOW_JOB_DIR must name an existing directory")
        return directory
    spool_root = Path(os.environ.get("WORKFLOW_DISPATCH_RUN_ROOT", "/tmp/ai-workflow-dispatch")).resolve()
    if spool_root == Path("/"):
        raise ValueError("WORKFLOW_DISPATCH_RUN_ROOT must not be the filesystem root")
    spool_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="dispatch-", dir=spool_root)).resolve()


def write_json_sidecar(path: Path, value: dict) -> None:
    """Atomically persist diagnostic detail that must not enter controller output."""

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


def main(argv: list[str]) -> int:
    if len(argv) != 7:
        raise ValueError("usage: dispatch.py claude-cli <label> <mode> <prompt-file> <artifact-root> <product-root>")
    target = read_target(argv[1])
    if target["id"] != "claude-cli":
        raise ValueError(f"{target['id']} is not a Claude relay target; use native Codex agents or the local-worker MCP")
    label, mode = argv[2], argv[3]
    mode = "artifact" if mode == "architecture" else mode
    if mode not in {"artifact", "execution"}:
        raise ValueError("mode must be artifact, architecture, or execution")
    if not label.startswith(target["label_prefix"]):
        raise ValueError(f"label must start with {target['label_prefix']}")
    prompt_path, artifact_root, product_root = (Path(value).resolve() for value in argv[4:7])
    if not prompt_path.is_file() or not artifact_root.is_dir() or not product_root.is_dir():
        raise ValueError("prompt file, artifact root, and product root must exist")
    prompt = prompt_path.read_text(encoding="utf-8")
    allowed, allowed_directories = allowed_paths(prompt, mode)
    if len(prompt) > target["hard_limits"]["max_prompt_chars"]:
        raise ValueError("prompt exceeds target hard limit")
    run_directory = dispatch_run_dir()
    changed_file_sample_limit = int(
        os.environ.get("WORKFLOW_CHANGED_FILE_SAMPLE_LIMIT", str(DEFAULT_CHANGED_FILE_SAMPLE_LIMIT))
    )
    if not 1 <= changed_file_sample_limit <= MAX_CHANGED_FILE_SAMPLE_LIMIT:
        raise ValueError(
            f"WORKFLOW_CHANGED_FILE_SAMPLE_LIMIT must be between 1 and {MAX_CHANGED_FILE_SAMPLE_LIMIT}"
        )

    artifact_before, product_before = snapshot(artifact_root), snapshot(product_root)
    run_root = artifact_root if mode == "artifact" else product_root
    # The shared Developer root contains both the product checkout and governed
    # artifact repository. Claude needs it for cross-repository context.
    shared_developer_root = Path(
        os.environ.get(
            "WORKFLOW_SHARED_CONTEXT_ROOT",
            os.path.commonpath([str(artifact_root), str(product_root)]),
        )
    ).resolve()
    if str(shared_developer_root) == "/":
        raise ValueError("shared context root must be explicitly bounded; refusing filesystem root")
    try:
        artifact_root.relative_to(shared_developer_root)
        product_root.relative_to(shared_developer_root)
    except ValueError as error:
        raise ValueError("shared context root must contain both artifact and product roots") from error
    allow_bash = mode == "artifact" and re.search(
        r"^WORKFLOW_CLAUDE_ALLOW_BASH=true$", prompt, re.MULTILINE
    ) is not None
    claude_tools = "Read,Glob,Grep,Write,Edit,Bash" if allow_bash else "Read,Glob,Grep,Write,Edit"
    resume_session = os.environ.get("WORKFLOW_CLAUDE_RESUME_SESSION")
    if resume_session is not None and not resume_session.strip():
        raise ValueError("WORKFLOW_CLAUDE_RESUME_SESSION must not be blank when set")
    command = [
        os.environ.get("WORKFLOW_CLAUDE_BINARY", "claude"), "-p", "--output-format", "stream-json", "--verbose",
        "--allowedTools", claude_tools,
    ]
    if resume_session:
        command.extend(["--resume", resume_session])
    command.extend(["--add-dir", str(shared_developer_root), "--", prompt])
    relay_result = run_claude_relay(
        command,
        cwd=run_root,
        run_dir=run_directory,
        timeout_seconds=None,
        stall_timeout_seconds=None,
        environment=os.environ.copy(),
    )
    completed = subprocess.CompletedProcess(
        command, relay_result.returncode, relay_result.stdout_summary, relay_result.stderr_summary
    )
    timed_out = relay_result.timed_out
    try:
        worker_summary = json.loads(relay_result.stdout_summary)
    except json.JSONDecodeError:
        worker_summary = {"summary_error": "relay returned invalid summary"}
    try:
        flow_control = json.loads(Path(relay_result.flow_control_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        flow_control = {"state": "BLOCKED", "reason": "unreadable_flow_control"}
    worker = {
        "kind": "external-claude-worker",
        "semantic_outcome": relay_result.semantic_outcome,
        "status_path": relay_result.status_path,
        "flow_control_path": relay_result.flow_control_path,
        "stream_path": relay_result.stream_path,
        "summary": worker_summary,
        "flow_control": flow_control,
    }
    artifact_changed = changed(artifact_before, snapshot(artifact_root))
    product_changed = changed(product_before, snapshot(product_root))
    if mode == "artifact":
        scope_violation = sorted(
            {path for path in artifact_changed if not path_is_allowed(path, allowed, allowed_directories)}
            | {f"product:{path}" for path in product_changed}
        )
    else:
        scope_violation = sorted(
            {f"artifact:{path}" for path in artifact_changed}
            | {
                f"product:{path}"
                for path in product_changed
                if not path_is_allowed(path, allowed, allowed_directories)
            }
        )
    audit_path = run_directory / "changed-files.json"
    write_json_sidecar(
        audit_path,
        {
            "artifact_changed_files": sorted(artifact_changed),
            "product_changed_files": sorted(product_changed),
            "scope_violation": scope_violation,
        },
    )
    outcome = "success" if completed.returncode == 0 and not scope_violation else "failed"
    if timed_out:
        outcome = "timeout"
    if worker:
        semantic_outcome = worker["semantic_outcome"]
        flow_state = worker["flow_control"].get("state")
        if semantic_outcome == "timeout":
            outcome = "timeout"
        elif semantic_outcome == "stalled":
            outcome = "stalled"
        elif semantic_outcome == "suspended" or flow_state == "SUSPENDED":
            # A provider can report rate-limit exhaustion as a generic terminal
            # error. Once the bounded relay has observed a sticky suspension,
            # preserve the completed scope audit and checkpoint rather than
            # silently classifying the recoverable boundary as a hard failure.
            outcome = "suspended"
        elif semantic_outcome != "success":
            outcome = "failed"
    if scope_violation:
        outcome = "scope-violation"
    artifact_sample, artifact_truncated = bounded_file_list(artifact_changed, limit=changed_file_sample_limit)
    product_sample, product_truncated = bounded_file_list(product_changed, limit=changed_file_sample_limit)
    violation_sample, violation_truncated = bounded_file_list(scope_violation, limit=changed_file_sample_limit)
    envelope = {
        "target": target["id"], "engine": target["engine"], "label": label, "mode": mode,
        "outcome": outcome, "exit_code": completed.returncode,
        "artifact_changed_file_count": len(artifact_changed), "artifact_changed_files": artifact_sample,
        "artifact_changed_files_truncated": artifact_truncated,
        "product_changed_file_count": len(product_changed), "product_changed_files": product_sample,
        "product_changed_files_truncated": product_truncated,
        "scope_violation_count": len(scope_violation), "scope_violation": violation_sample,
        "scope_violation_truncated": violation_truncated, "timed_out": timed_out,
        "changed_file_audit_path": str(audit_path),
        "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:],
    }
    if worker:
        envelope["worker"] = worker
    if outcome == "suspended" and worker:
        checkpoint_path = run_directory / "checkpoint.json"
        write_json_sidecar(
            checkpoint_path,
            {
                "schema_version": 1,
                "state": "SUSPENDED",
                "created_at_epoch": time.time(),
                "target": target["id"],
                "label": label,
                "mode": mode,
                "prompt_file": str(prompt_path),
                "artifact_root": str(artifact_root),
                "product_root": str(product_root),
                "session_id": worker["summary"].get("session_id"),
                "flow_control": worker["flow_control"],
                "changed_file_audit_path": str(audit_path),
            },
        )
        envelope["checkpoint_path"] = str(checkpoint_path)
    encoded_envelope = json.dumps(envelope, sort_keys=True)
    diagnostic_path = os.environ.get("WORKFLOW_DISPATCH_ENVELOPE_PATH")
    if diagnostic_path:
        write_json_sidecar(Path(diagnostic_path), envelope)
    print(encoded_envelope)
    return 0 if outcome == "success" else 6


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"outcome": "invalid-dispatch", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
