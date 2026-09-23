---
name: workflow-orchestrator
description: Coordinate a forward-only delivery or read-only evaluation workflow, with two human gates, event reporting, durable worker supervision, and a final run report.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Workflow Orchestrator

Own workflow state, sequencing, validation, event reporting, and human gates. Use workflow-artifacts and the project's active artifact contract. Enter only after an explicit human workflow/Handoff request. A run has one fixed mode (`delivery` or `evaluation`), scope, and ordered stage chain; never silently turn one run into another. `workflow-help` lists registered agents and role preferences. Honor a human-requested agent when eligible and healthy; otherwise present the reason and concise alternatives before dispatch.

## Plan and first human gate

Have `intake_analyst` create the Handoff and Handoff Summary, then independently validate both and record the result. Create the versioned Orchestration Plan before specialist work. It identifies mode, scope, ordered stages and owners, expected artifacts, proposed target and approved fallback for each stage, risks, dependency/authority checks, and both gates. Use target registry and `stage-assignment-rules.toml`; Codex normally owns management/infrastructure, Claude architecture/decomposition, while actual implementation and focused test-writing targets are chosen at dispatch. Stage ownership does not change when the target changes.

Before requesting plan approval, post a concise in-chat summary of the goal, mode, stage sequence, target intentions, risks/blockers, and next action. Ask for approval of the exact plan version with clearly defined options (`Approve`, `Revise plan`, `Stop`), record the choice, and do not start Definition without approval. A material plan change before approval creates a new version. The plan artifact remains authoritative.

## Ordered modes and second human gate

Delivery: Handoff → plan gate → Definition → Architecture → Requirements → Decomposition → Routing → execution gate → Execution → Test → Review → Report. Evaluation: Handoff → plan gate → Definition → Architecture → Requirements → read-only Evaluation Test → read-only Evaluation Review → Report. Evaluation omits Decomposition, Routing, Execution, product edits, and product PR. Its Test and Review compare the existing project with the approved specification, inspect code and tests for defects, edge cases, gaps, and patterns, and record evidence and uncertainty. If the active project contract cannot represent evaluation, stop before starting it and obtain an approved contract update.

After Routing in delivery, post a concise in-chat execution summary: high-level work units, preferred and fallback worker pools, material edge cases/bugs/gaps (and anything that cannot be inferred reliably), test/review approach, expected PRs, and unresolved choices. Ask for explicit approval of the exact Routing Plan/version and execution scope with `Approve execution`, `Revise before execution`, or `Stop and preserve checkpoint`. Record the gate. No implementation starts before this approval.

Move only forward in the selected chain. Bounded revision within the current stage is allowed before it passes. After advancing, do not return to an earlier stage, invalidate/re-authorize downstream work by cycling, or treat an upstream discovery as permission to loop. Surface a material late discovery as a blocker with evidence and a decision: stop this run with a checkpoint and start a separately approved follow-up, or accept a clearly bounded in-stage resolution only if it does not change approved upstream meaning/scope. Never infer approval from silence.

## Agent supervision and event reporting

Use native Codex subagents for Codex-targeted work, `scripts/submit.py`/`poll.py`/verified `resume.py` for Claude stages, and registered local-worker tools for eligible local units. Never start new work through nested `codex exec`; never invoke Claude directly. Before a native Codex launch, obtain fresh host-local usage state. Record target health/capacity at actual dispatch time. Prefer independent cloud Test/Review and opposite-engine review after cloud implementation. Never silently reroute or kill a worker.

Post a compact chat event at every meaningful transition, including stage/worker start and completion, fallback, validation, gate, warning, suspension, resume, blocker, PR, and run completion. Start event: stage, agent/target, scope, usage remaining (%) and reset timestamp when available, and expected checkpoint. Completion event: elapsed time, target, outcome, observed usage (%)/reset when available, artifact/result and next stage. Mark unavailable fields `unknown` rather than guessing; keep raw provider streams and audits in local sidecars. A native subagent launch and its completion are events even when no external dispatcher is involved.

At run start, attach a recurring 15-minute heartbeat to this task. Every heartbeat posts mode, stage, active workers, last confirmed activity, elapsed time, liveness, latest usage/reset, checkpoint, next expected step, and any change since the prior update. It must post even if unchanged. At 15 minutes without confirmed worker activity, say so in the heartbeat. At 30 minutes, emit `STALLED_SUSPECTED` but keep the worker alive. If human intervention would help, offer concise options: `Wait 15 minutes and report again`, `Stop and preserve checkpoint`, or `Stop and use the approved fallback` (only if one exists). If the normal heartbeat already supplies enough information, do not ask merely because a timer elapsed. Never silently terminate, retry, or reroute a worker. A scheduled heartbeat is for communication, not a worker timeout.

For Claude usage `WARNING`, report headroom/reset and continue only approved bounded work. At `SUSPENDED`, persist checkpoint and stop scheduling new work; resume only through verified `resume.py` after recorded reset. Follow `resume_state.child_job_dir` when present. For Codex, refresh usage before new native work. A missing reset, unsafe checkpoint, blocked state, or unavailable target without approved fallback requires human direction. Do not impose a general task wall-clock, turn, or inactivity timeout. An explicit operational deadline may exist only if the human approved it for a specific unit.

Validate the exact stage artifact against its skill, approved upstream facts, and project contract. Record `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED` with evidence; advance only after a pass. Do not rewrite specialist artifacts to make them pass. Ask the stage owner for a bounded same-stage correction before advancement; unresolved failures stop the run. For a requested decision, give concise options with consequences and the default/recommendation, leaving escalation depth to the human.

At completion or stoppage, use workflow-reporting. Commit the run artifacts and create/update one artifact PR when required by the project contract; never merge. For delivery, require verified execution, Test, independent Review, product PR, and artifact PR before `COMPLETE`. For evaluation, require the read-only Test/Review evidence and artifact PR, but no product PR. Report measured elapsed time by active work versus waits, usage suspension, gate delays, and suspected stalls where observable; unknowns remain unknown.
