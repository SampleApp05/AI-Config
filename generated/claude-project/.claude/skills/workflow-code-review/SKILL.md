---
name: workflow-code-review
description: Independently review the routed product diff, Test Report, and approved artifacts for actionable defects and residual risk. Use after Test; do not edit code, approve gates, or merge.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Code Review

Use the shared workflow-artifacts instructions and the project contract when available. In delivery mode, review the exact approved Requirements, Routing Plan, product diff or PR, implementation record, and Test Report. In evaluation mode, review the existing project against Definition, Architecture, Requirements, and the read-only Test Report; Routing Plan, implementation record, and product PR are not applicable. Select relevant domain skills. Stay read-only: do not edit product files, artifact files, or Git history. The reviewer must be independent of implementation; prefer Codex review after Claude implementation and Claude review after Codex implementation, with an independent cloud reviewer after local implementation.

Prioritize correctness, behavioral regressions, security, data integrity, compatibility, meaningful test gaps, and maintainability risks. Report actionable findings ordered by severity, with precise file/line evidence, expected versus actual behavior, and reproduction or reasoning where possible. Separate blocking findings, non-blocking findings, questions, and residual risks. If no finding is substantiated, say so and identify any evidence limits.

Return a structured review result for `code_reviewer/review-vN.md` (`REV-XXXX`) with mode, verdict `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED`, reviewed commit or PR (or baseline commit for evaluation), findings, Test Report reference, and remaining risks. Because this role is read-only, the orchestrator or coordinator may record the returned review without changing its substance; metadata must distinguish `performed_by: code_reviewer` from `recorded_by`. A review pass is not human approval or permission to merge. Findings do not cycle this run back to earlier stages; the orchestrator reports blockers or a separately approved follow-up.
