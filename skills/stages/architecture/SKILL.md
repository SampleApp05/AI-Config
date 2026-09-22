---
name: architecture
description: Assess and recommend the technical direction for a validated Definition, including whether existing architecture remains sufficient. Use relevant domain skills; do not implement or route work.
---

# Architecture

Use the shared workflow-artifacts instructions and the project contract. Work only from the exact validated Definition referenced by the approved run. Inspect existing architecture, code, ADRs, and domain context only as needed. Select relevant domain skills; do not invoke every domain skill merely because it is available.

Write `solution_architect/architecture-vN.md` (`ARC-XXXX`) with the Definition as parent. Describe architectural goals, affected components and boundaries, constraints, integration points, options and trade-offs in proportion to risk, a recommended direction, consequences, risks, assumptions, and human decisions required. Distinguish an approved decision from an agent recommendation. For simple or test-only work, a brief evidence-based assessment that existing architecture applies is valid; name what was checked, why no new decision is needed, and any residual risk. Do not invent alternatives to fill a template.

Escalate conflicts with approved decisions or material choices requiring human authority. Do not create requirements, implementation tasks, routes, or code changes. Self-check lineage and scope; request orchestrator validation and `READY_FOR_REQUIREMENTS` only after the artifact is ready. Never approve your own recommendation or gate.
