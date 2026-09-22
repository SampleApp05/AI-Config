#!/usr/bin/env python3
"""Validate shared definitions, generated outputs, and target consistency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

from mini_toml import load
import sync
from sync import ATRA_ARTIFACT_ROOT, CLAUDE_BUNDLE_ROOT, CODEX_ROOT, CONTROLLER_ROLE, MANIFEST_PATH, SHARED_ROOT, STAGE_SKILLS, DOMAIN_SKILLS, WORKFLOW_SKILLS, read_role, skill_source


REQUIRED_TARGET_FIELDS = {
    "id", "engine", "invocation", "workspace_host", "inference_host", "eligible_roles",
    "capabilities", "hard_limits", "permission_model", "health_check", "availability_policy",
    "capacity_policy", "latency_class", "cost_class", "default_fallback_chain", "label_prefix",
}


DERIVED_SOURCE_PREFIXES = ("role:", "skill:", "merge:", "mcp:")
PERMISSION_LEVELS = {"read-only", "workspace-write"}
WRITE_TOOL_NAMES = {"Edit", "Write", "NotebookEdit"}
PR_RESPONSIBILITIES = {"artifacts": "workflow_orchestrator", "product": "execution_coordinator"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shared_skill_names() -> set[str]:
    names = set(STAGE_SKILLS) | set(DOMAIN_SKILLS) | set(WORKFLOW_SKILLS)
    for path in (SHARED_ROOT / "skills" / "workflow").glob("*/SKILL.md"):
        names.add(path.parent.name)
    return names


def check_roles(failures: list[str], targets: dict) -> None:
    skills = shared_skill_names()
    active_roles = set()
    pr_owners: dict[str, str] = {}
    for path in sorted((SHARED_ROOT / "roles").glob("*.toml")):
        role = read_role(path)
        role_id = role.get("id")
        if role_id != path.stem:
            failures.append(f"{path.name}: role id must match the file name")
        if role.get("permission_level") not in PERMISSION_LEVELS:
            failures.append(f"{path.name}: invalid permission_level")
        status = role.get("status", "active")
        if status not in {"active", "reserved"}:
            failures.append(f"{path.name}: invalid status {status}")
        if status == "active":
            active_roles.add(role_id)
        pr_responsibility = role.get("pr_responsibility")
        if pr_responsibility:
            expected_role = PR_RESPONSIBILITIES.get(pr_responsibility)
            if expected_role != role_id:
                failures.append(f"{path.name}: invalid PR responsibility: {pr_responsibility}")
            elif pr_responsibility in pr_owners:
                failures.append(f"{path.name}: duplicate PR responsibility: {pr_responsibility}")
            else:
                pr_owners[pr_responsibility] = role_id
        for skill in role.get("owned_skills", []):
            if skill not in skills or not any(
                (SHARED_ROOT / "skills" / category / skill / "SKILL.md").is_file()
                for category in ("stages", "domains", "workflow")
            ):
                failures.append(f"{path.name}: owned skill does not exist: {skill}")
        codex_agent = CODEX_ROOT / "agents" / path.name
        claude_agent = CLAUDE_BUNDLE_ROOT / ".claude" / "agents" / ("workflow-stage-" + str(role_id).replace("_", "-") + ".md")
        if status == "reserved" and (codex_agent.exists() or claude_agent.exists()):
            failures.append(f"{path.name}: reserved role has a generated agent")
        if status == "active" and role_id != CONTROLLER_ROLE and not claude_agent.is_file():
            failures.append(f"{path.name}: Claude agent missing from the generated bundle")
    for target_id, record in targets.items():
        for role_id in record["eligible_roles"]:
            if role_id not in active_roles:
                failures.append(f"{target_id}: eligible role is not an active role: {role_id}")
    if pr_owners != PR_RESPONSIBILITIES:
        failures.append("role registry must assign artifact and product PR responsibilities exactly once")


def frontmatter(path: Path) -> dict:
    _, block, _ = path.read_text(encoding="utf-8").split("---", 2)
    result: dict = {}
    key = None
    for line in block.strip().split("\n"):
        if line.startswith("  - ") and key:
            result.setdefault(key, []).append(line[4:].strip())
        elif ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"') or []
    return result


def check_claude_bundle(failures: list[str]) -> None:
    agents_root = CLAUDE_BUNDLE_ROOT / ".claude" / "agents"
    skills_root = CLAUDE_BUNDLE_ROOT / ".claude" / "skills"
    bundled = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
    for path in skills_root.glob("*/SKILL.md"):
        if frontmatter(path).get("name") != path.parent.name:
            failures.append(f"{path}: skill name differs from its directory")
    seen = set()
    for path in sorted(agents_root.glob("*.md")):
        meta = frontmatter(path)
        name = meta.get("name")
        if name != path.stem or not str(name).startswith("workflow-stage-"):
            failures.append(f"{path.name}: agent name must equal the file name and start with workflow-stage-")
        if name in seen:
            failures.append(f"{path.name}: duplicate agent name")
        seen.add(name)
        tools = {tool.strip() for tool in str(meta.get("tools")).split(",")}
        if meta.get("permissionMode") == "plan" and tools & WRITE_TOOL_NAMES:
            failures.append(f"{path.name}: read-only agent has a write tool")
        for skill in meta.get("skills", []):
            if skill not in bundled and not (SHARED_ROOT / "skills" / "domains" / skill / "SKILL.md").is_file():
                failures.append(f"{path.name}: skill not available to Claude: {skill}")
    mcp = CLAUDE_BUNDLE_ROOT / ".mcp.json"
    if mcp.is_file():
        server = json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["local_worker"]
        for value in [server["command"]] + server["args"]:
            if not Path(value).exists():
                failures.append(f".mcp.json references a missing path: {value}")
    for path in CLAUDE_BUNDLE_ROOT.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            text = path.read_text(encoding="utf-8")
            if "/.codex" in text:
                failures.append(f"{path}: Claude bundle depends on a Codex-owned path")
            if re.search(r"\$[a-z][a-z-]*", text):
                failures.append(f"{path}: contains client-specific skill invocation syntax")


def main() -> int:
    failures: list[str] = []
    targets = {}
    for path in sorted((SHARED_ROOT / "targets").glob("*.toml")):
        if path.name == "stage-assignment-rules.toml":
            continue
        record = load(path)
        missing = REQUIRED_TARGET_FIELDS - record.keys()
        if missing:
            failures.append(f"{path.name}: missing target fields {sorted(missing)}")
        target_id = record.get("id")
        if not target_id or target_id in targets:
            failures.append(f"{path.name}: missing or duplicate target id")
        else:
            targets[target_id] = record
        limits = record.get("hard_limits", {})
        for limit in ("max_files", "max_context_bytes", "max_prompt_chars"):
            if not isinstance(limits.get(limit), int) or limits[limit] < 1:
                failures.append(f"{path.name}: invalid hard limit {limit}")
    for target_id, record in targets.items():
        for fallback in record["default_fallback_chain"]:
            if fallback not in targets:
                failures.append(f"{target_id}: unknown fallback {fallback}")

    for root in (SHARED_ROOT / "skills", SHARED_ROOT / "roles"):
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            text = path.read_text(encoding="utf-8")
            if "/Users/danielvelikov/.codex" in text or "~/.codex" in text:
                failures.append(f"{path}: contains a Codex-owned absolute path")
            if re.search(r"\$[a-z][a-z-]*", text):
                failures.append(f"{path}: contains client-specific skill invocation syntax")
            for referenced in re.findall(r"(?:target|target_id)\s*[:=]\s*[\"']([a-z0-9-]+)[\"']", text):
                if referenced not in targets:
                    failures.append(f"{path}: references unknown target {referenced}")

    if not MANIFEST_PATH.is_file():
        failures.append("generated manifest is missing")
    else:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for destination_text, record in manifest.get("outputs", {}).items():
            destination = Path(destination_text)
            if not destination.is_file():
                failures.append(f"generated output missing: {destination}")
                continue
            if digest(destination) != record["sha256"]:
                failures.append(f"generated output drift: {destination}")
            source = record["source"]
            if not source.startswith(DERIVED_SOURCE_PREFIXES):
                source_path = Path(source)
                if not source_path.is_file() or digest(source_path) != record["sha256"]:
                    failures.append(f"manifest source drift: {source}")

    for version in ("ARTIFACT-CONTRACT-v1.md", "ARTIFACT-CONTRACT-v1.1.md"):
        shared = SHARED_ROOT / "contract" / version
        asset = CODEX_ROOT / "skills" / "workflow-artifacts" / "assets" / version
        project = ATRA_ARTIFACT_ROOT / version
        if not all(path.is_file() for path in (shared, asset, project)):
            failures.append(f"contract copy missing: {version}")
        elif not (digest(shared) == digest(asset) == digest(project)):
            failures.append(f"contract copies diverge: {version}")

    for skill in ("atra-drizzle-postgres", "atra-feature-replay", "atra-market-streaming", "atra-service-platform", "atra-wallet-auth"):
        if (CODEX_ROOT / "skills" / skill).exists():
            failures.append(f"ATRA skill remains globally installed: {skill}")
        if not skill_source("projects/atra", skill).is_file():
            failures.append(f"ATRA source skill missing: {skill}")

    check_roles(failures, targets)
    check_claude_bundle(failures)

    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for project in manifest.get("claude_installs", []):
            if not Path(project).is_dir():
                failures.append(f"recorded Claude install target is missing: {project}")
        sync.DRY_RUN = True
        try:
            expected = sync.generate(manifest.get("claude_installs", []))
        finally:
            sync.DRY_RUN = False
        recorded = manifest.get("outputs", {})
        for destination, record in expected.items():
            if destination not in recorded:
                failures.append(f"generated output not in manifest (run sync): {destination}")
            elif recorded[destination]["sha256"] != record["sha256"]:
                failures.append(f"generated output stale against shared source (run sync): {destination}")
        for destination in recorded:
            if destination not in expected:
                failures.append(f"manifest lists an output no longer generated: {destination}")

    if failures:
        print("PARITY CHECK FAILED")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"PARITY CHECK PASSED: {len(targets)} targets and generated outputs match the manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
