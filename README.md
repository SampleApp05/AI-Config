# AI Workflow shared source

This directory is the engine-neutral source of truth for the governed workflow.

Client-specific files under `.codex`, `.claude`, and project repositories are generated compatibility outputs. Do not edit generated files directly; run `scripts/sync.sh` and use `scripts/parity-check.sh` to validate them.

The artifact repositories remain under `~/Developer/AI-Workflows/<Project>/`. This directory is the workflow definition root, not an artifact repository.

The current controller is Codex. It alone records validation, manifest, and human-gate state until a recorded controller handover occurs under Contract v1.1.

## Pull-request publication

Every governed run has two publication responsibilities. The `execution_coordinator` owns one product pull request for each product repository changed by the run; it opens or updates that PR after implementation and Test evidence is ready, then keeps it current through Review. The `workflow_orchestrator` owns exactly one artifact-repository PR for the whole run, including the final run report and every artifact produced by that run. Neither owner merges either PR. A required PR that cannot be created is a documented blocker, not a completed task.

## Claude Code mirror

Claude Code outputs are generated from the same roles and skills as Codex's, and are installed **per project** rather than globally:

```
scripts/sync.sh --install-claude <project directory>   # copy the bundle into <dir>/.claude and merge our MCP server into <dir>/.mcp.json
scripts/sync.sh --forget-claude <project directory>    # stop tracking an install (files stay in place)
```

The bundle (`generated/claude-project/`) contains one `workflow-stage-<role>` subagent per active role except `workflow_orchestrator`, `workflow-`-prefixed stage skills, `workflow-dispatch` (call any registered target through `scripts/dispatch.sh`), `workflow-controller` (main-session controller that honours `controller.engine` in the run manifest), and the shared `local_worker` MCP server (`mcp/local-worker/.venv`, created from `requirements.txt`). Subagents cannot spawn subagents, so the controller is a skill that calls stage agents one at a time. Read-only roles get `permissionMode: plan` and no write tools.

Domain skills (`backend`, `database`, ...) stay installed globally under `~/.claude/skills`. Reserved roles (`status = "reserved"`, currently `ux_designer`) are not generated for any engine.

## Checks

```
scripts/parity-check.sh          # registry, roles, skills, generated files vs. current sources, Claude bundle
python3 scripts/test_dispatch.py # dispatcher dry-run against mocked targets: scope, timeout, fallback, limits
```

## Long-running dispatch and usage guard

### Claude host authentication

Claude's existing CLI login may be unavailable to a Codex workspace-sandboxed launcher. Before starting a `claude-cli` job, run a minimal `claude -p` readiness check with narrowly scoped elevated host access, then launch `scripts/dispatch.sh start` with the same access only when that check returns `READY`. The detached supervisor and any automatic session resume then inherit the authenticated host environment. Status, wait, and usage reads remain sandboxed. Do not copy credentials, override `HOME`, disable sandboxing globally, or approve a broad shell/Python prefix; worker scope audit remains in force.

`scripts/dispatch.sh` runs every target as a supervised job. There is no turn limit.

```
scripts/dispatch.sh start  <target> <label> <mode> <prompt> <artifact-root> <product-root>   # detached, prints job_id
scripts/dispatch.sh wait   <job-id> --seconds 300      # block up to N seconds; exit 10 running, 11 suspended, else terminal
scripts/dispatch.sh status <job-id>                    # state, turns, last activity, usage, resume time
scripts/dispatch.sh cancel <job-id>
scripts/dispatch.sh usage  <target>                    # five-hour and weekly windows and the suspend decision
```

Policy lives in `targets/stage-assignment-rules.toml` (`[monitoring]`, `[usage]`): stall timeout (30 min without output), wall-clock backstop (4 h, 0 disables), status cadence (20 min), and the usage guard (suspend below 10% headroom in the five-hour window, block below 10% in the weekly window). A suspended job resumes its own Claude or Codex session after the window resets. Job state is in `state/jobs/` (git-ignored). Claude reports usage on its stream (`rate_limit_event`); Codex is read through `codex app-server` (`account/rateLimits/read`), so no model call is spent on it.

### Claude permissions

`targets/claude-cli.toml` `[permissions]` sets the profile. `developer` (default) allows Bash, web tools, and edits anywhere under `write_roots` (`~/Developer`), and passes those directories with `--add-dir`; without both, the CLI refuses ordinary commands such as `git add`, `mkdir`, `python3`, or `ls` on a sibling folder, and the run wastes usage. Denials are counted and the job stops at `max_permission_denials`. `scoped` restricts edits and Bash to the exact scope markers.
