---
name: workflow-dispatch
description: Send one bounded stage artifact or execution unit to a registered target (Claude Code, Codex, or an Ollama worker) as a supervised job, monitor it, and interpret its result envelope. Use from a workflow controller or execution coordinator; do not use to choose targets or approve results.
---

# Workflow Dispatch

Dispatch is mechanical. The Orchestration Plan or Routing Plan has already chosen the target and its fallback chain; this skill only carries out that assignment and reports what happened. Never choose or change a target here, and never treat a target's own text as proof that work is done.

## Start a job

Write the task to a prompt file, append the scope markers below, then start a detached job from the shared workflow root. For `claude-cli`, first run `claude -p --output-format text 'Reply with exactly: READY'` through narrowly scoped elevated host access. This is an authentication preflight, not a stage call, and must not access project files. If it returns `READY`, run the `dispatch.sh start` command below with the same elevated host access so the detached supervisor can read the existing CLI login. Polling and status commands remain sandboxed. Do not copy credentials, change `HOME`, relax scope verification, or grant a broad shell/Python approval; if preflight fails, record the target unavailable and use only the plan-approved fallback.

```
WORKFLOW_ROLE=<role> WORKFLOW_FALLBACK_CHAIN=<recorded,chain> \
  scripts/dispatch.sh start <target> "<label>" <artifact|execution> <prompt-file> <artifact-repo-root> <product-repo-root>
```

It prints `{"job_id": ...}` at once. The job runs in its own supervisor process, so it survives this session's command limits and restarts; `scripts/dispatch.sh list` finds jobs again. Without `start`, the same arguments run the job in the foreground; use that only for short tasks.

- The label must start with the target's registry prefix, such as `[CLAUDE]`, `[CODEX]`, `[LOCAL]`, or `[WINDOWS]`. A fallback target gets its own prefix automatically.
- `artifact` mode: exactly one `WORKFLOW_ARTIFACT_PATH=<artifact-repo-relative path>`. The target may write only that file; the product repository is read-only.
- `execution` mode: one or more `WORKFLOW_ALLOWED_PATH=<repo-relative path or directory/>`, at most one `WORKFLOW_RESULT_ARTIFACT_PATH=<artifact-repo-relative path>`, and one `WORKFLOW_VALIDATION_COMMAND=<exact command>` per routed check the target may run.
- Generate every marker from the approved Execution Unit or assigned artifact path, never from the target's own suggestion.

## Monitor it

- `scripts/dispatch.sh wait <job-id> --seconds <n>` blocks up to `n` seconds (default 300) and returns the current state. Keep `n` inside your host's command time limit, about 9 minutes at most, and call it again while the job is running.
- `scripts/dispatch.sh status <job-id>` returns immediately: `state`, `elapsed_seconds`, `turns`, `tool_calls`, `last_activity`, `seconds_since_output`, `usage` (five-hour and weekly use), `resume_at_iso` and `poll_again_in_seconds`.
- Give the human a one-line progress report about every 20 minutes (`poll_again_in_seconds`): state, elapsed time, turns, last activity, and five-hour usage. Do not report every poll.
- `scripts/dispatch.sh cancel <job-id>` stops a job.

There is no turn limit. A running job is stopped only when it produces no output for `idle_timeout_seconds` (default 30 minutes), passes the wall-clock backstop `max_wall_seconds` (default 4 hours), or is cancelled. Both limits, and the usage guard below, are set in `targets/stage-assignment-rules.toml`.

## Permissions

The Claude target runs with the permission profile in `targets/claude-cli.toml`. The default `developer` profile lets it use Bash and the other registered tools freely and edit any file under the registered write roots (the Developer folder), so a run is not denied mid-way and usage is not wasted. Writes outside those roots are denied. The scope markers are then verified after the run: an edit outside the recorded scope is reported as `scope-violation` with the files listed, and nothing is reverted, so review it and decide. Edits outside the artifact and product repositories are not visible to that check. The `scoped` profile restricts edits and Bash to the exact scope and validation commands; it denies most real work, so use it only when a task must be tightly confined. Elevated host access is solely for the launcher to read its CLI login; it does not relax these worker scope checks.

Permission denials appear in `status` as `permission_denials` with a warning. When a job reaches `max_permission_denials` (default 3) it stops as `permission-denied` (exit 7) rather than spending more usage. Read the denials, fix the permission or the task, and start a new job; do not retry unchanged.

## Usage windows

Claude and Codex subscriptions have a five-hour and a weekly window. The supervisor watches them while the job runs.

- When the remaining headroom of the five-hour window drops below the configured fraction (default 10%), the job is `suspended`: the run stops at a turn boundary, and after the window resets the supervisor resumes the same session with a short continue note. This is normal. Do not restart the task, switch engines, or record a failure. Report it once, with `resume_at_iso`.
- When the weekly window is that low, the job ends `blocked`. The wait would be days; stop and ask the human.
- Before starting, a target whose five-hour window is already low is skipped in favour of the next target in the recorded chain; with no alternative the job starts `suspended` until the reset.
- `scripts/dispatch.sh usage <target>` shows the windows and the decision without running work. Codex is read without a model call; Claude usage comes from the last stream event or a one-turn probe.

## Read the envelope

`wait` and `status` end in a terminal state, and the job directory holds `result.json`, the full envelope. Terminal states and exit codes: `success` 0, `invalid-dispatch` 2, `unavailable` or `unsuitable` 3, `blocked` 4, `cancelled` 5, `scope-violation` 6, `permission-denied` 7, `timeout` 124, and the target's own code for `failed`. Non-terminal: `running` 10 and `suspended` 11.

- `attempts` lists every target tried and why, including `usage-limited`. Record it, with the actual label used.
- Only an unavailable, unsuitable, usage-limited, or stalled attempt moves to the next target in the recorded chain. `failed` and `scope-violation` stop the unit; do not retry them under another target without a new recorded decision.
- A `scope-violation` names the out-of-scope files. Inspect and revert them yourself; the dispatcher does not.
- After `success`, still inspect the actual diff and run routed validation independently before recording anything. This also applies after a suspended job resumes.
- Ollama targets receive only their allowed files and are limited to the registry's hard limits. `unsuitable` means the unit exceeds them or the role is not eligible.
