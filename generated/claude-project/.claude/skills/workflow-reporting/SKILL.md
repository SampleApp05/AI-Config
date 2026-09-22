---
name: workflow-reporting
description: Produce a durable Workflow Run Report at completion or stoppage using verified stage artifacts, gate records, backend events, warnings, and agent outcomes. Do not rewrite source artifacts or conceal failures.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Workflow Reporting

Use the shared workflow-artifacts instructions and the project contract. The controller writes `workflow_orchestrator/workflow-run-report-vN.md` (`WRUN-XXXX`) at completion or stoppage. Read the approved plan, manifest, validation and approval records, stage artifacts, execution record, Test Report, and Review. Use only observed facts; mark unavailable metrics as unknown rather than estimating them as actuals.

Include workflow identity and final status; goal and approved scope; stage-by-stage artifact IDs, versions, validation, and transitions; agents, backends, and high-level effort profiles; routed versus actual assignments; fallback and retry reasons; advisory budget warnings; product commits and PR when verified; test/review outcomes; rework and partial progress; residual risks; and required human actions. For each agent, summarize assignment, result quality against its contract, timeliness only if measured, rework, and notable limitations. Avoid unsupported numerical rankings or attributing a system problem to an agent without evidence.

Distinguish workflow completion from product merge. Preserve failed and blocked gates, unresolved findings, and incomplete actions. The report is a synthesis and index, not a replacement for primary artifacts. A material correction creates a new version and preserves the old one.
