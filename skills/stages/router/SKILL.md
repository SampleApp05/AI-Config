---
name: router
description: Assess complexity and turn validated Decomposition Work Units into a safe execution Routing Plan with preferred backends, effort profiles, fallback, and validation. Do not implement work.
---

# Router

Use the shared workflow-artifacts instructions and the project contract. Use the exact validated Decomposition for the approved run, with Requirements and Architecture only as needed. Work Units say **what** exists; the Router decides **how** to execute it. Preserve scope and dependencies. All normal workflows pass through this stage; a small concern may become one Execution Unit.

For each Work Unit, assess complexity, risk, context size, uncertainty, dependencies, file overlap, required domain skills, validation needs, and local-resource suitability. The Router owns the final complexity assessment; no classifier agent is required. Shape bounded `EU-XX` Execution Units and record source Work Unit, purpose, allowed scope and files, inputs, dependencies, expected outputs, acceptance mapping, validation commands, checkpoint, and escalation conditions. A local unit requires a verified absolute Git root and explicit repository-relative file allowlist.

Write `execution_router/routing-plan-vN.md` (`ROUTE-XXXX`) with the chosen target, target rationale, registered fallback chain, availability condition, high-level effort profile when relevant, and advisory budget for each unit. Resolve target facts from `WORKFLOW_SHARED_ROOT/targets/` and apply `stage-assignment-rules.toml`; never hard-code model names, endpoint addresses, client paths, or a provider-specific fallback. A target identifies where inference runs and where the workspace and tools run. Evaluate capability fit, risk, context and file limits, target health, availability, capacity, and independence. An Ollama target is eligible only for an independently verifiable unit that fits every registered hard limit. The workspace, Git operations, tests, and validation remain on the declared workspace host.

Use the selected target's registry label prefix, such as `[CODEX]`, `[CLAUDE]`, `[LOCAL]`, or `[WINDOWS]`. Labels and status checks are observational, not locks. Under manual monitoring, serialize work on each resource-constrained target by plan and require human direction if that target is visibly busy. Keep code-editing units in the declared product repository and artifacts in the separate workflow repository. An unavailable, unsuitable, or timed-out dispatch triggers only its recorded fallback; do not wait indefinitely for a target.

Budgets are estimates and warning thresholds, not automatic stop conditions. Safety, authority, missing information, unavailable backends without approved fallback, and failed gates may block. Self-check coverage, acyclic dependencies, safe parallelism, valid labels, fallback, and validation; request orchestrator validation and `READY_FOR_IMPLEMENTATION`. Do not implement or change upstream decisions.
