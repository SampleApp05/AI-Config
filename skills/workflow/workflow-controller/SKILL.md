---
name: workflow-controller
description: Run a governed workflow as the controlling session when the manifest names Claude as controller, calling stage agents one at a time and recording validation, manifest state, gates, and controller handovers. Use only on an explicit human request to run or resume a workflow.
---

# Workflow Controller (Claude session)

This skill makes the current main session the workflow controller. It adds Claude-specific mechanics to the shared orchestrator rules; read and follow `workflow-orchestrator` for the stage chain, validation statuses, gates, and run report, and `workflow-artifacts` for the repository and contract.

## Before anything else

1. Require an explicit human request to start or resume a workflow. Ordinary discussion is not entry.
2. Read the project's `project.yaml`, the newest `ARTIFACT-CONTRACT-v*.md`, and the run's `manifest.yaml`.
3. Continue only if `controller.engine` is `claude`. If it is `codex`, stop: report that Codex holds control and offer the handover below. Never write controller-owned records for a run another controller holds.

## Calling stages

Subagents cannot start other subagents, so this session calls stage agents itself, one at a time, and waits for each to finish. Role `<role_id>` maps to the subagent `workflow-stage-<role_id with hyphens>`, for example `problem_analyst` to `workflow-stage-problem-analyst`. The orchestrator role is this session; the reserved `ux_designer` role is not callable.

For each specialist stage, use the target the approved Orchestration Plan or Routing Plan recorded:

- Target `claude-cli`: call the stage subagent natively. Give it the exact artifact path or allowed files. Afterwards verify with `git status` and `git diff` in the artifact or product repository that only that scope changed; revert nothing silently, report a breach.
- Any other target (`codex`, `mac-ollama`, `windows-4070`) or a fresh isolated Claude process: use `workflow-dispatch` with the plan's recorded fallback chain. Start the job, then poll it with `wait` (each Bash call under about 9 minutes) and give the human a one-line progress report about every 20 minutes.
- A native subagent call has no stall detection or usage guard. Use `workflow-dispatch` for any unit expected to take more than a few minutes, and for any run that could approach the five-hour usage window.
- Read-only roles (`code_reviewer`) return their result to you. You record it unchanged in the artifact, with `performed_by` set to the role and `recorded_by` to you.

## What stays yours

You own the manifest, validation records, approval records, and the run report. Validate each returned artifact against its stage skill and the contract, record `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED`, and advance only after a pass. Human gates (Handoff, plan approval, overrides) are never delegated or assumed; ask in chat and record only an actual decision. A stage agent's success claim is not evidence; inspect the diff and run routed validation yourself. After the final run report, commit the complete artifact branch and create or update the one required artifact-repository PR; verify its URL and state, never merge it, and treat publication failure as `BLOCKED`.

## Controller handover

Handover moves control between Codex and Claude. It happens only at a stage boundary, when every completed artifact is validated and nothing is in flight.

1. Ask the human to decide: name the run, the current and proposed controller, the last validated artifact version, and open blockers.
2. On a clear yes, write `workflow_orchestrator/controller-handover-vN.md` with the prior controller, new controller, effective artifact version, the human decision quoted with its date, and the validation state of every completed stage.
3. Update the manifest: `controller.engine` to the new controller, `controller.handover.status: handed-over`, `recorded_by`, and `record` pointing to that file. Do not rewrite earlier artifacts.
4. Commit, push, and create or update a PR only when the approved contract assigns that publication responsibility; never merge.

A target assignment never changes who the controller is.
