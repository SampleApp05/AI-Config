"""Read the shared target registry without client-specific configuration."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from mini_toml import load


SHARED_ROOT = Path(__file__).resolve().parents[2]
TARGETS_ROOT = SHARED_ROOT / "targets"
REQUIRED_TARGET_FIELDS = {
    "id",
    "engine",
    "invocation",
    "workspace_host",
    "inference_host",
    "eligible_roles",
    "capabilities",
    "hard_limits",
    "permission_model",
    "health_check",
    "availability_policy",
    "capacity_policy",
    "latency_class",
    "cost_class",
    "default_fallback_chain",
    "label_prefix",
}


def load_targets() -> dict[str, dict]:
    """Load all target records, rejecting incomplete or duplicate definitions."""
    targets: dict[str, dict] = {}
    for path in sorted(TARGETS_ROOT.glob("*.toml")):
        if path.name == "stage-assignment-rules.toml":
            continue
        target = load(path)
        missing = REQUIRED_TARGET_FIELDS - target.keys()
        if missing:
            raise ValueError(f"target registry record {path.name} is missing: {sorted(missing)}")
        target_id = target["id"]
        if target_id in targets:
            raise ValueError(f"duplicate target id: {target_id}")
        targets[target_id] = target
    return targets


def resolve_target(target_id: str) -> dict:
    """Resolve a canonical id or a documented legacy alias."""
    for canonical_id, target in load_targets().items():
        if target_id == canonical_id or target_id in target.get("legacy_aliases", []):
            return target
    raise ValueError(f"unknown target: {target_id}")


def assignment_rules() -> dict:
    return load(TARGETS_ROOT / "stage-assignment-rules.toml")
