#!/usr/bin/env python3
"""Generate client compatibility outputs from the shared workflow source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import ast


SHARED_ROOT = Path(__file__).resolve().parents[1]
USER_ROOT = Path("/Users/danielvelikov")
CODEX_ROOT = USER_ROOT / ".codex"
CLAUDE_ROOT = USER_ROOT / ".claude"
ATRA_ROOT = USER_ROOT / "Developer" / "Atra-Services"
ATRA_ARTIFACT_ROOT = USER_ROOT / "Developer" / "AI-Workflows" / "Atra"
MANIFEST_PATH = SHARED_ROOT / "generated" / "manifest.json"
CLAUDE_BUNDLE_ROOT = SHARED_ROOT / "generated" / "claude-project"
DRY_RUN = False  # parity checks plan every output without touching disk

STAGE_SKILLS = [
    "handoff", "workflow-orchestrator", "definition", "architecture", "requirements",
    "decomposition", "router", "execution", "testing", "code-review",
    "workflow-reporting", "implementation", "intake",
]
DOMAIN_SKILLS = ["android", "backend", "database", "infrastructure", "integration", "ios", "security", "web"]
WORKFLOW_SKILLS = ["workflow-api-documentation", "workflow-artifacts"]
ATRA_SKILLS = [
    "atra-drizzle-postgres", "atra-feature-replay", "atra-market-streaming",
    "atra-service-platform", "atra-wallet-auth",
]
FROZEN_SKILLS = {"ios"}
# Claude project bundle: workflow-namespaced skills and stage agents, installed per project rather than globally.
CLAUDE_BUNDLE_WORKFLOW_SKILLS = ["workflow-artifacts", "workflow-dispatch", "workflow-controller"]
CONTROLLER_ROLE = "workflow_orchestrator"  # runs as the main-session controller skill, not as a subagent
READ_ONLY_TOOLS = "Read, Glob, Grep, Bash"
WRITE_TOOLS = "Read, Edit, Write, Glob, Grep, Bash"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_output(source: Path, destination: Path, outputs: dict[str, dict], *, frozen: bool = False) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = digest(source)
    if DRY_RUN or (destination.exists() and digest(destination) == source_hash):
        outputs[str(destination)] = {"source": str(source), "sha256": source_hash, "frozen": frozen}
        return
    if frozen:
        raise RuntimeError(f"frozen output differs and will not be overwritten: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    outputs[str(destination)] = {"source": str(source), "sha256": source_hash, "frozen": frozen}


def skill_source(category: str, skill: str) -> Path:
    return SHARED_ROOT / "skills" / category / skill / "SKILL.md"


def read_role(path: Path) -> dict:
    """Parse the deliberately small, portable TOML subset used by role files."""
    role: dict = {"scope": {}}
    section: dict = role
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[scope]":
            section = role["scope"]
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value.startswith("["):
            value = ast.literal_eval(raw_value)
        elif raw_value.startswith('"'):
            value = ast.literal_eval(raw_value)
        else:
            value = raw_value
        section[key] = value
    return role


def write_agent(role: dict, destination: Path, outputs: dict[str, dict]) -> None:
    role_id = role["id"]
    skills = role["owned_skills"]
    instructions = role["scope"]["instruction"]
    forbidden = "; ".join(role["forbidden_actions"])
    lines = [
        f'name = "{role_id}"',
        f'description = "{role["description"]}"',
        f'sandbox_mode = "{role["permission_level"]}"',
        "",
        'developer_instructions = """',
        "This file is generated from the shared workflow role registry.",
        instructions,
        f"Forbidden actions: {forbidden}.",
        "Use only the generated owned skills and the shared artifact contract.",
        '"""',
        "",
    ]
    for skill in skills:
        lines.extend([
            "[[skills.config]]",
            f'path = "/Users/danielvelikov/.codex/skills/{skill}/SKILL.md"',
            "enabled = true",
            "",
        ])
    content = "\n".join(lines)
    source_key = f"role:{role_id}"
    write_text_output(content, destination, outputs, source_key)


def write_text_output(content: str, destination: Path, outputs: dict[str, dict], source_key: str) -> None:
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    if not DRY_RUN and (not destination.exists() or digest(destination) != content_hash):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    outputs[str(destination)] = {"source": source_key, "sha256": content_hash, "frozen": False}


def claude_skill_name(skill: str) -> str:
    """Stage skills get a workflow- prefix in Claude; domain and workflow-* skills keep their names."""
    return f"workflow-{skill}" if skill in STAGE_SKILLS and not skill.startswith("workflow-") else skill


def render_claude_skill(source: Path, name: str) -> str:
    _, frontmatter, body = source.read_text(encoding="utf-8").split("---", 2)
    frontmatter = "\n".join(f"name: {name}" if line.startswith("name:") else line for line in frontmatter.split("\n"))
    notice = (
        f"\n> Shared workflow root for this installation: `{SHARED_ROOT}`. "
        "Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.\n"
    )
    return f"---{frontmatter}---{notice}{body}"


def render_claude_agent(role: dict) -> tuple[str, str]:
    role_id = role["id"]
    name = "workflow-stage-" + role_id.replace("_", "-")
    read_only = role["permission_level"] == "read-only"
    skills = "\n".join(f"  - {claude_skill_name(skill)}" for skill in role["owned_skills"])
    lines = [
        "---",
        f"name: {name}",
        f'description: "{role["description"]} Called by the workflow controller for the {role["scope"]["stage"]} stage; not for general use."',
        f"tools: {READ_ONLY_TOOLS if read_only else WRITE_TOOLS}",
    ]
    if read_only:
        lines.append("permissionMode: plan")
    if skills:
        lines.extend(["skills:", skills])
    scope_rule = (
        "You are read-only. Do not modify any file. Return your full result as `artifact_markdown` in the envelope; the controller records it unchanged."
        if read_only else
        "Write only the exact artifact path or allowed files named in the task. Never write the manifest, validation records, approval records, run report, or another agent's artifact."
    )
    publication_rule = (
        "As the execution coordinator, create or update only the assigned product PR after the required evidence is satisfactory; verify and report its URL, branches, commit, and state. Never merge or force-push."
        if role.get("pr_responsibility") == "product" else
        "Do not commit, push, open or update a PR, merge, or claim approval. Do not treat your own success as acceptance."
    )
    lines.extend([
        "---",
        "",
        "This file is generated from the shared workflow role registry. Do not edit it.",
        "",
        f"You are the `{role_id}` agent in a governed workflow. The workflow controller (Codex or Claude, named in the run manifest) owns validation, the manifest, and every human gate.",
        "",
        role["scope"]["instruction"],
        "",
        f"Forbidden: {'; '.join(role['forbidden_actions'])}.",
        "",
        "Rules:",
        "- Start only from the approved upstream artifacts and the task the controller gives you. Read the project's newest ARTIFACT-CONTRACT before authoring a formal artifact.",
        f"- {scope_rule}",
        f"- {publication_rule}",
        "- Report honestly: list what you verified, what you could not, and any assumption you made.",
        "",
        "Finish with a single JSON object and no other text:",
        "",
        '{"outcome": "SUCCESS|PARTIAL_SUCCESS|FAILED|BLOCKED|ESCALATED", "summary": "", "artifact_paths": [], "artifact_ids": [], "artifact_markdown": null, "changed_files": [], "pull_requests": [], "validation": [{"command": "", "outcome": "", "notes": ""}], "assumptions": [], "risks": [], "blockers": []}',
        "",
    ])
    return name, "\n".join(lines)


def claude_mcp_config() -> str:
    server = SHARED_ROOT / "mcp" / "local-worker"
    config = {"mcpServers": {"local_worker": {
        "command": str(server / ".venv" / "bin" / "python"),
        "args": [str(server / "server.py")],
    }}}
    return json.dumps(config, indent=2, sort_keys=True) + "\n"


def build_claude_bundle(outputs: dict[str, dict]) -> None:
    """Generate the per-project Claude bundle inside the shared root."""
    skills_root = CLAUDE_BUNDLE_ROOT / ".claude" / "skills"
    for skill in STAGE_SKILLS:
        name = claude_skill_name(skill)
        write_text_output(render_claude_skill(skill_source("stages", skill), name), skills_root / name / "SKILL.md", outputs, f"skill:{skill}")
    for skill in CLAUDE_BUNDLE_WORKFLOW_SKILLS:
        write_text_output(render_claude_skill(skill_source("workflow", skill), skill), skills_root / skill / "SKILL.md", outputs, f"skill:{skill}")
    for version in ("ARTIFACT-CONTRACT-v1.md", "ARTIFACT-CONTRACT-v1.1.md"):
        copy_output(SHARED_ROOT / "contract" / version, skills_root / "workflow-artifacts" / "assets" / version, outputs)
    for role_path in sorted((SHARED_ROOT / "roles").glob("*.toml")):
        role = read_role(role_path)
        if role.get("status", "active") == "reserved" or role["id"] == CONTROLLER_ROLE:
            continue
        name, content = render_claude_agent(role)
        write_text_output(content, CLAUDE_BUNDLE_ROOT / ".claude" / "agents" / f"{name}.md", outputs, f"role:{role['id']}")
    write_text_output(claude_mcp_config(), CLAUDE_BUNDLE_ROOT / ".mcp.json", outputs, "mcp:local_worker")


def install_claude_bundle(project: Path, outputs: dict[str, dict]) -> None:
    """Copy the bundle into a project's .claude directory, merging only our MCP server into .mcp.json."""
    for source in sorted(CLAUDE_BUNDLE_ROOT.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(CLAUDE_BUNDLE_ROOT)
        destination = project / relative
        if relative.as_posix() == ".mcp.json":
            existing = json.loads(destination.read_text(encoding="utf-8")) if destination.is_file() else {}
            existing.setdefault("mcpServers", {})["local_worker"] = json.loads(source.read_text(encoding="utf-8"))["mcpServers"]["local_worker"]
            write_text_output(json.dumps(existing, indent=2, sort_keys=True) + "\n", destination, outputs, "merge:.mcp.json")
        else:
            copy_output(source, destination, outputs)


def installed_projects() -> list[str]:
    if MANIFEST_PATH.is_file():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("claude_installs", [])
    return []


def generate(installs: list[str] | None = None) -> dict[str, dict]:
    outputs: dict[str, dict] = {}
    codex_skills = CODEX_ROOT / "skills"
    for skill in STAGE_SKILLS:
        copy_output(skill_source("stages", skill), codex_skills / skill / "SKILL.md", outputs)
    for skill in DOMAIN_SKILLS:
        copy_output(skill_source("domains", skill), codex_skills / skill / "SKILL.md", outputs, frozen=skill in FROZEN_SKILLS)
    for skill in WORKFLOW_SKILLS:
        copy_output(skill_source("workflow", skill), codex_skills / skill / "SKILL.md", outputs)
    copy_output(
        SHARED_ROOT / "contract" / "ARTIFACT-CONTRACT-v1.md",
        codex_skills / "workflow-artifacts" / "assets" / "ARTIFACT-CONTRACT-v1.md",
        outputs,
    )
    copy_output(
        SHARED_ROOT / "contract" / "ARTIFACT-CONTRACT-v1.1.md",
        codex_skills / "workflow-artifacts" / "assets" / "ARTIFACT-CONTRACT-v1.1.md",
        outputs,
    )
    for metadata in (SHARED_ROOT / "metadata" / "codex").glob("*/openai.yaml"):
        skill = metadata.parent.name
        if skill in ATRA_SKILLS:
            continue
        copy_output(metadata, codex_skills / skill / "agents" / "openai.yaml", outputs)

    for role_path in sorted((SHARED_ROOT / "roles").glob("*.toml")):
        role = read_role(role_path)
        if role.get("status", "active") == "reserved":
            continue
        write_agent(role, CODEX_ROOT / "agents" / role_path.name, outputs)

    claude_global_skills = ["android", "backend", "database", "infrastructure", "integration", "security", "web"]
    for skill in claude_global_skills:
        copy_output(skill_source("domains", skill), CLAUDE_ROOT / "skills" / skill / "SKILL.md", outputs)
    copy_output(skill_source("domains", "ios"), CLAUDE_ROOT / "skills" / "ios" / "SKILL.md", outputs, frozen=True)
    copy_output(skill_source("workflow", "workflow-api-documentation"), CLAUDE_ROOT / "skills" / "workflow-api-documentation" / "SKILL.md", outputs)
    copy_output(SHARED_ROOT / "adapters" / "claude" / "skills" / "workflow-executor" / "SKILL.md", CLAUDE_ROOT / "skills" / "workflow-executor" / "SKILL.md", outputs)
    for adapter in (SHARED_ROOT / "adapters" / "claude" / "agents").glob("*.md"):
        copy_output(adapter, CLAUDE_ROOT / "agents" / adapter.name, outputs)

    for skill in ATRA_SKILLS:
        source = skill_source("projects/atra", skill)
        copy_output(source, ATRA_ROOT / ".claude" / "skills" / skill / "SKILL.md", outputs)
        copy_output(source, ATRA_ROOT / ".agents" / "skills" / skill / "SKILL.md", outputs)

    copy_output(SHARED_ROOT / "contract" / "ARTIFACT-CONTRACT-v1.md", ATRA_ARTIFACT_ROOT / "ARTIFACT-CONTRACT-v1.md", outputs)
    copy_output(SHARED_ROOT / "contract" / "ARTIFACT-CONTRACT-v1.1.md", ATRA_ARTIFACT_ROOT / "ARTIFACT-CONTRACT-v1.1.md", outputs)

    build_claude_bundle(outputs)
    for project in (installed_projects() if installs is None else installs):
        install_claude_bundle(Path(project), outputs)
    return outputs


def main(argv: list[str]) -> int:
    installs = installed_projects()
    if argv[1:2] == ["--install-claude"]:
        if len(argv) != 3 or not Path(argv[2]).is_dir():
            print("usage: sync.py --install-claude <existing project directory>")
            return 2
        project = str(Path(argv[2]).resolve())
        if project not in installs:
            installs.append(project)
    elif argv[1:2] == ["--forget-claude"]:
        # Stops tracking an install target; installed files stay in place.
        if len(argv) != 3:
            print("usage: sync.py --forget-claude <project directory>")
            return 2
        installs = [path for path in installs if path != str(Path(argv[2]).resolve())]
    elif len(argv) > 1:
        print("usage: sync.py [--install-claude <project directory> | --forget-claude <project directory>]")
        return 2
    outputs = generate(installs)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "claude_installs": sorted(installs), "outputs": outputs}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Generated and verified {len(outputs)} compatibility outputs.")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
