---
name: workflow-code-review
description: Independently review the routed product diff, Test Report, and approved artifacts for actionable defects and residual risk. Use after Test; do not edit code, approve gates, or merge.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Code Review

Use the shared workflow-artifacts instructions and the project contract when available. Review the exact approved Requirements, Routing Plan, product diff or PR, implementation record, and Test Report. Select relevant domain skills. Stay read-only: do not edit product files, artifact files, or Git history.

Prioritize correctness, behavioral regressions, security, data integrity, compatibility, meaningful test gaps, and maintainability risks. Report actionable findings ordered by severity, with precise file/line evidence, expected versus actual behavior, and reproduction or reasoning where possible. Separate blocking findings, non-blocking findings, questions, and residual risks. If no finding is substantiated, say so and identify any evidence limits.

Return a structured review result for `code_reviewer/review-vN.md` (`REV-XXXX`) with verdict `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED`, reviewed commit or PR, findings, Test Report reference, and remaining risks. Because this role is read-only, the orchestrator or coordinator may record the returned review without changing its substance; metadata must distinguish `performed_by: code_reviewer` from `recorded_by`. A review pass is not human approval or permission to merge.
