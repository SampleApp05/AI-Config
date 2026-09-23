---
name: workflow-requirements
description: Turn validated Architecture into a traceable, testable delivery contract for the approved workflow run. Do not redesign architecture, decompose, route, or implement.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Requirements

Use the shared workflow-artifacts instructions and the project contract. Use the exact validated Architecture and approved decisions for this run. Write `requirements_engineer/requirements-vN.md` (`REQ-XXXX`) with Architecture lineage. State only applicable functional, non-functional, behavioral, interface, data, and integration requirements. Give each requirement a stable ID, trace its source, and provide verifiable acceptance criteria. Mark inapplicable categories only when useful; do not invent filler.

For a small task, the delivery contract may be brief, but must still make correctness and completion testable. Preserve scope and architecture. Distinguish explicit decisions from derived assumptions and identify blocking questions. Do not prescribe implementation tasks, agents, backend choices, or test code. Escalate contradictions or new product decisions rather than resolving them yourself.

Self-check traceability, testability, version, location, and lineage. Request orchestrator validation and `READY_FOR_DECOMPOSITION` in delivery mode or `READY_FOR_EVALUATION_TEST` in evaluation mode; do not force a transition or edit upstream artifacts.
