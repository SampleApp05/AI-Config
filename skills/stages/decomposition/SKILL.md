---
name: decomposition
description: Turn validated Requirements into bounded, traceable Work Units and dependencies for an approved delivery run. Do not select workers or execution backends.
---

# Decomposition

Use the shared workflow-artifacts instructions and the project contract. This stage is mandatory for delivery mode and omitted for evaluation mode. Read the exact validated Requirements for the approved delivery run, plus upstream context only as needed. Write `work_planner/decomposition-vN.md` (`DEC-XXXX`) with stable `WORK-001`-style unit IDs. Each unit states purpose, requirement references, scope, inputs, outputs, affected areas, constraints, risks, observable completion criteria, and typed dependencies (`HARD`, `SOFT`, `EXTERNAL`, or `INFORMATIONAL`).

Cover every significant requirement and trace every unit to a requirement. Detect overlap, gaps, cycles, external blockers, and safe parallelism. Keep the result proportionate: a simple change may have one Work Unit. Do not create artificial units merely to increase detail. Provide complexity signals such as uncertainty, risk, and context needs, but leave final complexity assessment, effort profile, and backend choice to the Router.

Do not change product scope, architecture, or requirements; do not assign agents, models, or routes. Self-check coverage and dependencies, then request orchestrator validation and `READY_FOR_ROUTING`. Escalate blocking upstream ambiguity or conflict to stop the current run or obtain a separately approved follow-up; do not cycle backward.
