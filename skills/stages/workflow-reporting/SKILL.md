---
name: workflow-reporting
description: Produce a durable Workflow Run Report at completion or stoppage using verified stage artifacts, gate records, backend events, warnings, and agent outcomes. Do not rewrite source artifacts or conceal failures.
---

# Workflow Reporting

Use the shared workflow-artifacts instructions and the project contract. The controller writes `workflow_orchestrator/workflow-run-report-vN.md` (`WRUN-XXXX`) at completion or stoppage. Read the approved plan, manifest, validation and approval records, stage artifacts, execution record, Test Report, and Review. Use only observed facts; mark unavailable metrics as unknown rather than estimating them as actuals.

Include workflow mode, identity, and final status; goal and approved scope; both human gates in delivery (only the plan gate in evaluation); stage-by-stage artifact IDs, versions, validation, and transitions; agents, backends, and high-level effort profiles; routed preferences versus actual dispatch assignments; fallback and retry reasons; advisory budget warnings; product commits and PRs when applicable, the single artifact PR, and their verified URLs/branches/states; test/review outcomes; rework and partial progress; residual risks; and required human actions. Summarize event and 15-minute heartbeat coverage, liveness warnings, stalls, suspensions, and the disposition of each. Break down measured active work, usage waits, gate waits, and stalled/unknown time where evidence permits. For each agent, summarize assignment, result quality against its contract, timeliness only if measured, rework, and notable limitations. Avoid unsupported numerical rankings or attributing a system problem to an agent without evidence.

Distinguish workflow completion from product merge. Preserve failed and blocked gates, unresolved findings, and incomplete actions. The report is a synthesis and index, not a replacement for primary artifacts. A material correction creates a new version and preserves the old one.
