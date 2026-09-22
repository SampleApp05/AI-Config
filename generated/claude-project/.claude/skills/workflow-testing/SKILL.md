---
name: workflow-testing
description: "Own the formal Test stage after implementation: design, add, and run tests against Requirements and actual code, classify failures, and produce a Test Report. Do not silently alter production behavior."
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Testing

Use the shared workflow-artifacts instructions and the project contract. Use the exact approved Requirements, routed units, implementation results, and actual product diff. Select relevant domain skills and existing test conventions. Design the smallest sufficient suite for acceptance criteria, edge cases, regressions, and material risks; explain coverage gaps rather than inventing meaningless tests.

Edit only allowed test files, fixtures, and test-only support. Run deterministic test commands and record command, environment, outcome, and relevant evidence. Classify each failure as implementation defect, test defect, environment issue, or unresolved. Fix a test defect within your scope; return a production defect to execution rather than silently modifying production code. A failed or unavailable test is not a pass.

Write `test_engineer/test-report-vN.md` (`TEST-XXXX`) with requirement and unit coverage, tests added or changed, executions and results, failure classification, gaps, risks, and verdict (`PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or `BLOCKED`). Keep it concise for small work but never omit the outcome and evidence. Request orchestrator validation and return implementation defects to the coordinator. Do not approve a PR, merge, or change requirements.
