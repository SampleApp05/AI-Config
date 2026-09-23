---
name: workflow-testing
description: "Own the formal Test stage after implementation: design, add, and run tests against Requirements and actual code, classify failures, and produce a Test Report. Do not silently alter production behavior."
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Testing

Use the shared workflow-artifacts instructions and the project contract. In delivery mode, use the exact approved Requirements, routed units, implementation results, and actual product diff. Select relevant domain skills and existing test conventions. Design the smallest sufficient suite for acceptance criteria, edge cases, regressions, and material risks; explain coverage gaps rather than inventing meaningless tests. A focused test-writing execution unit may use a healthy local worker, but the formal Test verdict and evidence remain independently owned here.

In evaluation mode, compare the existing project with the approved Requirements without editing product code, tests, fixtures, or Git history. Inspect and run existing tests when safe; analyze acceptance coverage, edge cases, bugs, test gaps, and behavioral patterns. Record unverified claims as such. A missing test is a finding, not authorization to add one.

In delivery mode, edit only allowed test files, fixtures, and test-only support. Run deterministic test commands and record command, environment, outcome, and relevant evidence. Classify each failure as implementation defect, test defect, environment issue, or unresolved. Return a production defect as a finding; after the workflow advances beyond Execution, do not send it backward in the same run. The orchestrator decides whether to stop and open a separately approved follow-up. A failed or unavailable test is not a pass.

Write `test_engineer/test-report-vN.md` (`TEST-XXXX`) with mode, requirement coverage, tests executed, results, failure classification, gaps, risks, and verdict (`PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED`). In evaluation mode state `tests added or changed: none`; routed-unit coverage is not applicable. Keep it concise for small work but never omit outcome and evidence. Request orchestrator validation. Do not approve a PR, merge, or change requirements.
