---
name: definition
description: Produce a solution-independent Definition from the approved workflow Handoff after the human Orchestration Plan gate. Do not design architecture or implement work.
---

# Definition

Use the shared workflow-artifacts instructions and the project contract. Work only within the approved run identified by its manifest and Orchestration Plan. Read the latest eligible validated `HANDOFF` and companion summary for that run; do not choose an unrelated artifact by recency. Preserve explicit human decisions above inference. Stop for a blocking conflict or ambiguity rather than inventing intent.

Write `problem_analyst/definition-vN.md` (`DEF-XXXX`) with lineage to the exact Handoff version. Include the problem statement, context, desired outcomes, in/out scope, observable success criteria, affected areas, constraints, dependencies, risks, assumptions, and open questions. Label blocking questions. Keep the definition solution-independent: no technology selection, architecture, technical requirements, task assignment, or routing. For a narrow concern, make the artifact concise but still demonstrate the boundaries and success condition.

Self-check clarity, scope, lineage, metadata, and absence of unresolved blocking questions. Request orchestrator validation and the `READY_FOR_ARCHITECTURE` transition; do not perform either yourself. Revise only your own draft after a failed validation. Do not modify Handoff, downstream artifacts, or product code.
