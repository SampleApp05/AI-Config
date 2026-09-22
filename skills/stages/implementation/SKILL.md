---
name: implementation
description: Implement one approved Routing Plan execution unit in the product repository and return a concise, verifiable result. Do not redesign, reroute, approve, or merge work.
---

# Implementation

Load the routed unit and its approved context. Use the shared workflow-artifacts instructions when you can access the artifact repository; otherwise use the bounded assignment supplied by the execution coordinator. Treat allowed files, acceptance criteria, dependencies, and validation as a contract. Select only relevant domain skills.

Edit the shared product workspace directly. Make the smallest coherent change, preserve existing user work, and avoid unrelated refactors. Do not change approved architecture, requirements, route, or scope. Run only permitted relevant checks and report changed files, commands/outcomes, assumptions, risks, warnings, and blockers. A model-generated description is not proof: the coordinator will inspect the actual diff and validate independently.

When able to write artifacts, create `implementation_worker/implementation-result-<unit-id>-vN.md` (`IMPL-XXXX`) with the routed unit and product-code references. When working through an external backend that cannot access the artifact repo, return the same concise facts; the coordinator records them as `recorded_by` while preserving you as `performed_by`. Do not paste large diffs into chat or artifact files unless requested.

Do not commit, push, open a PR, or merge unless the execution coordinator's approved unit explicitly assigns that operation. Advisory budget excess is a warning, but hard permissions, safety, and scope boundaries still apply.
