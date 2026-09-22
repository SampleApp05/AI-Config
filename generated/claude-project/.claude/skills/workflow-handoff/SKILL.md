---
name: workflow-handoff
description: Convert an explicit user request to enter the workflow, plus relevant discussion, into a traceable Handoff and Handoff Summary. Use before Definition; do not design or implement the solution.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Handoff

Use this skill only when the human explicitly requests a Handoff or initiates a workflow. Ordinary exploration, brainstorming, and discussion remain conversation, not a workflow entry.

Use the shared workflow-artifacts instructions and the project's artifact contract. Select the project, technology, and feature from the current human request and relevant context. If technology ownership is genuinely cross-stack, use `Cross-Stack`; do not duplicate one decision into several technology runs. Confirm the artifact repository exists before writing. The controller assigns a project-wide unique `WF-XXXX` and creates the run manifest; if no ID has been assigned, request one rather than inventing a conflicting ID.

Read only the relevant discussion and referenced project context. Preserve what the human wants and why, alternatives considered, actual decisions, constraints, deferred options, and unresolved questions. Distinguish explicit fact, explicit decision, assumption, inference, and unknown. A discussed possibility is not an approved decision. Record source chat titles or IDs where available without copying entire transcripts. If a current instruction conflicts with an approved artifact, or intent cannot be interpreted meaningfully, stop and ask the human.

Write `intake_analyst/handoff-vN.md` with `HAND-XXXX` identity and sections: Intent; Problem / Motivation; Goal; Scope (In and Out); Known Constraints; Explicit Decisions; Assumptions; Open Questions; Expected Outcome. Write the companion `handoff-summary-vN.md` with its own `HSUM-XXXX` identity, a reference to the primary Handoff, and concise sections: Need; Context; What Was Considered; Decision; Why; Important Constraints; Deferred / Out of Scope; Open Questions; Future Reference. Use `None identified` where a required field is genuinely absent. The primary Handoff is authoritative; the summary is contextual.

Self-check naming, metadata, linkage, accuracy, scope, assumptions, and blocking ambiguity. Request orchestrator validation; do not approve or advance the gate yourself. On a blocking ambiguity or conflict, explain the issue and ask a specific question. Do not choose architecture, requirements, tasks, routes, technologies, workers, or implementation details that the human has not decided.
