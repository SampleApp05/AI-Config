# Workflow Artifact Contract — v1.1

Version 1.1 is backward compatible with v1. Existing v1 artifacts remain valid and do not need to be rewritten. New or revised artifacts may add the v1.1 ownership and assignment fields below.

## Repository boundary

Each project has a separate artifact repository under `~/Developer/AI-Workflows/<Project>/`. Product repositories contain product changes; artifact repositories contain decisions, plans, evidence, approvals, validation records, and run history. Neither repository stores credentials, full session transcripts, or pasted product patches.

## Workflow path

`Handoff → Orchestration Plan → human approval → Definition → Architecture → Requirements → Decomposition → Router → Execution → Test → Review → Run Report`

Handoff and Orchestration Plan approval are human-gated. They are never delegated to a local or external target. The workflow controller records validation, manifest state, and human-gate records unless a recorded controller handover says otherwise.

## Ownership

Artifacts retain v1 `performed_by` and `recorded_by` fields. v1.1 adds:

```yaml
ownership:
  performed_by: solution_architect
  recorded_by: workflow_orchestrator
  engine: claude-code
  target_id: claude-cli
```

`engine` identifies the execution engine; `target_id` is a registered target. The executing engine writes only its assigned formal artifact. The controller validates that same artifact and alone updates controller-owned state.

## Manifest additions

```yaml
controller:
  engine: codex
  handover:
    status: not-handed-over
    recorded_by: workflow_orchestrator
    record: null

stage_assignments:
  - stage: architecture
    role: solution_architect
    target: claude-cli
    rationale: capability fit and independent technical direction
    fallback_chain: [codex, mac-ollama]
    health_observation: checked-at-dispatch
```

`controller.engine` is `codex` or `claude`. A change requires an explicit handover record identifying the prior and new controller, effective artifact version, human decision, and validation state. A target assignment never changes controller ownership.

## Assignment and scope

The approved Orchestration Plan records an evaluated assignment for every eligible specialist stage. The Router records the same information for every Execution Unit. Assignments cite a target registry entry and consider capability fit, risk, context, health, availability, capacity, and independence.

Artifact authoring may write only its exact assigned artifact path. Execution may write only the allowed files recorded in its Execution Unit. A target response is evidence, not acceptance; scope violations, failed validation, missing authority, or failed human gates stop progression.

## Compatibility

All v1 identifiers, lineage, validation statuses, manifest states, versioning rules, and artifact-folder conventions remain valid. New v1.1 fields are additive. The authoritative copies of v1 and v1.1 reside in the shared workflow root and are generated into the project artifact repository and workflow-artifacts skill asset.
