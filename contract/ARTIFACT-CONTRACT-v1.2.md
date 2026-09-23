# Workflow Artifact Contract — v1.2

Version 1.2 extends v1.1 for new delivery and evaluation runs. Existing v1/v1.1 runs and artifacts remain governed by their recorded contract; do not retroactively rewrite them. All v1/v1.1 repository, identity, ownership, validation, scope, and PR rules apply except where explicitly refined below.

## Fixed mode and forward-only stages

Record `contract_version: 1.2` and `mode: delivery` or `mode: evaluation` in the run manifest and approved Orchestration Plan. A run's mode cannot change after plan approval.

Delivery: Handoff → Orchestration Plan → human plan approval → Definition → Architecture → Requirements → Decomposition → Routing → human execution approval → Execution → Test → Review → Run Report.

Evaluation: Handoff → Orchestration Plan → human plan approval → Definition → Architecture → Requirements → read-only Test → read-only Review → Run Report. The existing `test_engineer/test-report-vN.md` and `code_reviewer/review-vN.md` paths and `TEST`/`REV` IDs are used. Decomposition, Routing, Execution, product edits, and product PR are `NOT_APPLICABLE` with the mode as evidence; no placeholder artifacts are created. Evaluation compares the existing project's verified baseline commit with approved requirements and reports bugs, edge cases, logic gaps, test gaps, patterns, uncertainty, and residual risks. It does not implement fixes.

A stage may revise its own draft before validation. Once the run advances, it never returns to an earlier stage. A material late discovery blocks the current run and is recorded for a separately approved follow-up unless a bounded resolution within the current stage leaves approved upstream meaning and scope unchanged. Do not invalidate and regenerate downstream artifacts by cycling within the same run. No human gate may be inferred from silence.

## Human gates

The plan gate records the exact `OPLAN` version in `workflow_orchestrator/plan-approval-vN.md` (`HAPP` ID). Delivery additionally records approval of the exact Routing Plan/version and execution scope in `workflow_orchestrator/execution-approval-vN.md` (a distinct `HAPP` ID). No implementation begins before the second gate. Record the human's decision, source, conditions, and time if observed. Evaluation has no execution gate.

Before each gate, publish a concise in-chat decision summary. The plan summary names scope, mode, ordered stages, proposed targets/fallbacks, risks, and the approval action. The execution summary names high-level units, worker pools, key edge cases/bugs/gaps, unresolved choices, validation/review strategy, and expected PRs. Present distinct concise options; never treat a summary as approval.

## Assignment and evidence

The Orchestration Plan records role preferences and approved fallbacks. Routing records eligible preferred/fallback pools for execution units, not an irrevocably fixed executor. At actual dispatch, record fresh health and usage, chosen target, rationale, and any fallback in the Execution record and manifest. Codex-targeted work uses native subagents; Claude stages use the approved durable relay; local workers are eligible only within their registered limits. An implementer cannot independently review its own work.

The controller keeps a compact, append-only event journal at `workflow_orchestrator/events.jsonl` for stage/worker start and completion, validation, gates, usage warnings, suspension/resume, fallback, blockers, PRs, and 15-minute heartbeats. Each record includes an observed timestamp, event type, stage, agent/target when applicable, and known elapsed/usage/reset/checkpoint fields; unknown values are explicitly unknown. The journal is controller state, not a replacement for formal artifacts or human approval records. The 15-minute quiet and 30-minute `STALLED_SUSPECTED` classifications are observational; they do not authorize killing or rerouting a worker. Any stop/fallback for a live worker requires an explicit human decision and preserved checkpoint.

The Run Report distinguishes measured work time, gate waits, usage suspension, and suspected stalls where evidence permits. In evaluation, an artifact PR is still required under v1.1 publication rules, while a product PR is `NOT_APPLICABLE` with verified no-edit evidence. Delivery requires both PR types as applicable. Never claim a PR, merge, or outcome without verification.
