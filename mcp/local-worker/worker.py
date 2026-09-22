"""Host-agnostic bounded Aider work driven entirely by the target registry."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from threading import Lock
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from registry import SHARED_ROOT, resolve_target


_activity_lock = Lock()
_active_target = None  # type: Optional[str]


def target_config(target_id: str) -> dict:
    target = resolve_target(target_id)
    if target["engine"] != "ollama-aider":
        raise ValueError(f"target is not a local worker target: {target['id']}")
    return target


def ollama_model_available(base_url: str, model: str) -> tuple[bool, str]:
    try:
        with urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=3) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        return False, f"Ollama health check failed: {type(error).__name__}"
    models = payload.get("models") if isinstance(payload, dict) else None
    names = {entry.get("name") for entry in models if isinstance(entry, dict)} if isinstance(models, list) else set()
    if model not in names:
        return False, "Configured model is not listed by Ollama"
    return True, "available"


def _allowed_paths(repository: Path, allowed_files: list[str]) -> list[Path]:
    if not allowed_files:
        raise ValueError("allowed_files must not be empty")
    result: list[Path] = []
    root = repository.resolve()
    for relative in allowed_files:
        if not relative or Path(relative).is_absolute():
            raise ValueError("allowed_files must be repository-relative paths")
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("allowed file escapes the repository")
        result.append(candidate)
    return result


def unit_suitable(target: dict, repository: Path, allowed_files: list[str], prompt: str) -> tuple[bool, str]:
    limits = target["hard_limits"]
    if len(allowed_files) > limits["max_files"]:
        return False, f"{target['id']} supports at most {limits['max_files']} files per unit"
    if len(prompt) > limits["max_prompt_chars"]:
        return False, f"{target['id']} prompt exceeds the registered limit"
    total_bytes = 0
    for path in _allowed_paths(repository, allowed_files):
        if not path.exists() or not path.is_file():
            return False, f"allowed file does not exist: {path.relative_to(repository)}"
        total_bytes += path.stat().st_size
    if total_bytes > limits["max_context_bytes"]:
        return False, f"selected files exceed the {target['id']} context limit"
    return True, "suitable"


def status() -> dict:
    with _activity_lock:
        active = _active_target
    results: dict[str, dict] = {}
    for target_id in ("mac-ollama", "windows-4070"):
        target = target_config(target_id)
        available, reason = ollama_model_available(target["ollama_base_url"], target["model"])
        results[target_id] = {"available": available, "reason": reason}
    return {"active_target": active, "targets": results}


def run_local_worker(
    label: str,
    repository: str,
    allowed_files: list[str],
    prompt: str,
    timeout_seconds: int = 900,
    target: str = "mac-ollama",
) -> dict:
    target_record = target_config(target)
    if not label.startswith(target_record["label_prefix"]):
        raise ValueError(f"label must start with {target_record['label_prefix']}")
    if not isinstance(timeout_seconds, int) or not 30 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty")
    repo = Path(repository).resolve()
    if not repo.is_dir():
        raise ValueError("repository must be an existing directory")
    suitable, reason = unit_suitable(target_record, repo, allowed_files, prompt)
    if not suitable:
        return {"status": "unsuitable", "target": target_record["id"], "reason": reason, "review_required": False}
    available, reason = ollama_model_available(target_record["ollama_base_url"], target_record["model"])
    if not available:
        return {"status": "unavailable", "target": target_record["id"], "reason": reason, "review_required": False}
    with _activity_lock:
        global _active_target
        if _active_target is not None:
            return {"status": "busy", "target": target_record["id"], "reason": f"{_active_target} is active", "review_required": False}
        _active_target = target_record["id"]
    try:
        command = [
            target_record["local_worker"]["aider_command"],
            "--yes-always",
            "--no-auto-commits",
            "--no-git",
            "--model",
            f"ollama_chat/{target_record['model']}",
            "--edit-format",
            "diff",
            "--message",
            prompt,
            *allowed_files,
        ]
        settings_name = target_record.get("local_worker", {}).get("model_settings_file")
        if settings_name:
            command.extend(["--model-settings-file", str(SHARED_ROOT / "mcp" / "local-worker" / settings_name)])
        environment = dict(os.environ)
        environment["OLLAMA_API_BASE"] = target_record["ollama_base_url"]
        result = subprocess.run(command, cwd=repo, timeout=timeout_seconds, text=True, capture_output=True, env=environment, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "target": target_record["id"], "timeout_seconds": timeout_seconds, "review_required": True}
    except OSError as error:
        return {"status": "failed", "target": target_record["id"], "reason": str(error), "review_required": True}
    finally:
        with _activity_lock:
            _active_target = None
    return {
        "status": "success" if result.returncode == 0 else "failed",
        "target": target_record["id"],
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "review_required": True,
    }
