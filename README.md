# AI Workflow shared source

This repository holds the maintained skill, target, contract, local-worker, and adapter sources. The active Codex workflow root is `~/.codex/AI-Workflow`; governed run artifacts remain only in `~/Developer/AI-Workflows/<Project>/`. `scripts/sync.sh` generates client skill/agent copies from this source. Do not use older generated instructions as workflow authority.

## Modes and gates

Delivery runs Handoff → plan approval → Definition → Architecture → Requirements → Decomposition → Routing → execution approval → Execution → Test → Review → Report. Evaluation runs Handoff → plan approval → Definition → Architecture → Requirements → read-only Test → read-only Review → Report. A run moves forward only; late material discoveries become blockers or separately approved follow-ups, not stage loops. Contract v1.2 records these rules and adds controller event/heartbeat evidence. Existing runs retain their original contract.

Before each gate, the orchestrator posts the concise plan or execution summary and asks for an explicit choice. Every stage/worker start and completion, gate, validation, fallback, usage transition, blocker, and PR receives a compact chat event. A thread-attached heartbeat posts status every 15 minutes, even if unchanged. At 15 minutes without confirmed activity it notes the silence; at 30 minutes it reports `STALLED_SUSPECTED` while keeping the worker alive. Human intervention is requested only when useful, with a 15-minute wait/report option. No automatic turn, wall-clock, or inactivity limit is imposed on workflow tasks.

## Targets

`workflow-help` lists the active agents, role preferences, and capabilities. Codex management/infrastructure and other Codex-targeted work use native subagents, never nested `codex exec`. Claude is preferred for architecture and decomposition and runs through the durable relay (`~/.codex/AI-Workflow/scripts/dispatch.sh`, `submit.py`, `poll.py`, and verified `resume.py`). Codex is preferred for Requirements. Implementation and focused test-writing workers are selected at dispatch from the approved pool after fresh health and usage checks. Both registered local workers remain configured; their endpoints and models were preserved. Formal Test/Review are independent, with opposite-engine review preferred after cloud implementation.

The relay stores full provider streams and changed-file audits in private local sidecars; only compact worker/flow-control state enters chat. Usage suspension preserves a checkpoint and pauses new scheduling. A live slow worker is not silently killed or rerouted. A local worker has no default task timeout; any explicit unit deadline needs human approval.

### Claude host authentication

Claude stages require the host's existing Claude CLI login. Before a `claude-cli` dispatch, the controller runs a minimal `claude -p` readiness check outside Codex's workspace sandbox, then launches `submit.py`—and any later `resume.py` continuation—with the same narrowly scoped host access. This preserves the relay's artifact/path audit while allowing each child process to see the authenticated CLI session. Polling remains sandboxed. Never copy credentials into the workspace, change `HOME`, or grant broad shell/Python access; use a reusable approval limited to the shared workflow launchers when available.

## Checks and generation

Run `python3 -m unittest discover -s scripts -p 'test_*.py'` and `python3 -m unittest discover -s mcp/local-worker -p 'test_*.py'` from this repository. `scripts/sync.sh` regenerates Codex and Claude skill copies plus contract assets; inspect planned outputs before using it on a workspace with active user changes. Never merge or force-push product or artifact PRs as part of sync.
