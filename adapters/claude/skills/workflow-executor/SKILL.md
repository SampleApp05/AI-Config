---
name: workflow-executor
description: Complete a bounded Codex-dispatched stage or execution task, authoring only an explicitly assigned formal artifact, and return structured evidence. Use in any governed project; do not control workflow state, approve gates, or expand scope.
---

# Workflow Executor

Use this skill only when the prompt contains an approved Codex workflow label and artifact context.

## Operating contract

- Treat the task label, supplied artifact IDs, allowed files, dependencies, acceptance criteria, and validation instructions as binding.
- When the dispatch assigns a formal stage artifact, read the supplied project `ARTIFACT-CONTRACT-v1.md` and write only the exact artifact path and version named in the task. Keep the artifact in its owning agent folder, preserve its required metadata and lineage, self-check it, and request Codex validation. Do not write a manifest, validation record, approval record, routing plan, execution record, or workflow report unless that artifact is explicitly your assigned stage output.
- An Architecture dispatch normally writes `solution_architect/architecture-vN.md` (`ARC-XXXX`) from the validated Definition. Analyse the supplied evidence; document direction, boundaries, trade-offs, assumptions, risks, and open decisions. Do not create requirements, work units, routes, code changes, or a gate result.
- An execution dispatch makes only the requested product changes within the approved workspace and file scope. If it is also assigned an implementation-result artifact, write only that exact file in the supplied artifact repository; the execution coordinator still owns the execution record.
- Load only the domain skill relevant to the task. Project-specific skills may be supplied by that project's local configuration.

## Return format

Return a single JSON object and no Markdown:

```json
{
  "outcome": "SUCCESS | PARTIAL_SUCCESS | FAILED | BLOCKED | ESCALATED",
  "summary": "short factual result",
  "artifact_paths": [],
  "artifact_ids": [],
  "changed_files": [],
  "validation": [{ "command": "", "outcome": "", "notes": "" }],
  "assumptions": [],
  "risks": [],
  "blockers": [],
  "escalation": []
}
```

The formal artifact is Claude's stage output. Codex independently validates that same artifact, records validation and manifest state, and owns human gates. Never treat a model response as proof that workflow acceptance has passed.
