# Workflow Artifact Contract — v1

## Repository and taxonomy

Each project owns a separate Git repository at `~/Developer/AI-Workflows/<Project>/`. The product-code repository remains separate. This repository stores decisions, plans, evidence, approvals, validation records, and run history; it does not store code patches, secrets, or full chat transcripts.

The initial technology folders are `Backend`, `Database`, `Web`, `iOS`, `Android`, `Infrastructure`, `Security`, `Integration`, and `Cross-Stack`. Add a new technology folder only when a real workflow needs it and record the addition in the project index. `Cross-Stack` owns one feature-level workflow spanning multiple technologies; it may reference technology-specific child workflows. Never duplicate authoritative feature decisions across child workflows.

The run path is:

```text
<Project>/<Technology>/workflows/<feature-slug>/<workflow-id>/
```

Use lowercase kebab-case for `<feature-slug>` and a project-wide unique `WF-XXXX` workflow ID. Create the workflow folder only for a real Handoff. The technology is the primary subject of the work, not the worker provider or model. The run's `manifest.yaml` records project, technology, feature, workflow ID, related workflow IDs, source context, and current gate state.

## Run layout and ownership

```text
manifest.yaml
intake_analyst/                 handoff-vN.md, handoff-summary-vN.md
workflow_orchestrator/         orchestration-plan-vN.md, plan-approval-vN.md,
                              validations/<artifact-id>-vN.md, workflow-run-report-vN.md
problem_analyst/               definition-vN.md
solution_architect/            architecture-vN.md; optional decision records
requirements_engineer/        requirements-vN.md
work_planner/                  decomposition-vN.md
execution_router/             routing-plan-vN.md
execution_coordinator/        execution-record-vN.md
implementation_worker/        implementation-result-<unit-id>-vN.md
test_engineer/                 test-report-vN.md
code_reviewer/                 review-vN.md
```

Create agent folders when the agent first produces an artifact. All stage agents are called in the normal chain; a simple stage may produce a concise, reasoned confirmation of existing context, but not an empty artifact. Each agent may revise only its own unvalidated draft. The orchestrator may update the manifest and its own records, but must not rewrite a specialist artifact. For a read-only reviewer or external worker unable to access the artifact repo, the coordinator may record the returned result in that role's folder without changing its substance; metadata must distinguish `performed_by` and `recorded_by`.

## Identity and metadata

Every Markdown artifact starts with YAML metadata equivalent to:

```yaml
---
artifact:
  id: ARC-0001
  type: ARCHITECTURE
  version: 1
  status: DRAFT
workflow:
  id: WF-0001
  project: Atra
  technology: Backend
  feature: wallet-verification
lineage:
  parents:
    - DEF-0001@v1
ownership:
  created_by: solution_architect
---
```

Use the established type prefixes: `HAND`, `HSUM`, `OPLAN`, `DEF`, `ARC`, `REQ`, `DEC`, `ROUTE`, `EXEC`, `IMPL`, `TEST`, `REV`, `WRUN`, `VAL`, and `HAPP`. An artifact ID is unique within its project repository; `@vN` identifies an exact version. The filename version and metadata version must match. Record referenced artifact IDs and paths, and include product-repository commit or PR references only when verified. Never invent timestamps, hashes, validation outcomes, or human decisions.

## Versioning, validation, and gates

Start at `v1`. A material revision creates `v2`, leaving `v1` intact. The manifest points to the latest eligible version; it is an index, not a substitute for evidence. A revised upstream artifact makes dependent downstream versions stale until revalidated or regenerated. A Git commit does not by itself mean validation or approval.

The author self-checks its draft and requests validation. The orchestrator, acting as workflow controller, checks the artifact against this contract, its stage contract, its upstream lineage, and the approved orchestration plan. It writes a validation record with `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED`, then updates the manifest. It cannot validate its own Orchestration Plan into human approval. A failed or blocked gate stops progression; advisory budget overruns are warnings, not failed gates.

The Orchestration Plan is the first mandatory human gate. The approval record must identify the exact plan artifact ID and version, the human decision and its source, any conditions, and the approving human. A material plan revision needs a new approval. Silence is never approval. Only a human may override a failed gate, approved decision, or scope boundary; the override must be recorded with its exact target and reason.

Use `DRAFT`, `VALIDATED`, `APPROVED`, `BLOCKED`, and `SUPERSEDED` as the primary manifest states, with stage-specific transition detail where needed. Do not mark an artifact approved merely because its author finished it. Keep validation and approval records after supersession for auditability.

## Git and external references

Commit the approved plan and validated stage outputs at meaningful checkpoints on a workflow branch, normally `workflow/<workflow-id>-<feature-slug>`. Do not automatically merge an artifact-repository branch; record the PR or merge status if one exists. Exact branch and PR policy may be set by the project without weakening gates. Never force-push or erase approved history.

Reference the product repository by verified repository identity, commit, branch, and PR when available. The implementation worker edits the product repository directly; its artifact records changed files and outcomes, not a pasted patch. Local model assignments receive only the bounded files and context needed for their unit. Human-facing labels identify the actual backend, such as `[CODEX][EXEC]`, `[CLAUDE][EXEC]`, or `[LOCAL][EXEC]`; labels are observational, not resource locks.
