---
name: workflow-artifacts
description: Apply the shared repository layout, artifact metadata, versioning, validation, and approval rules when creating or reading governed workflow artifacts. Use with a workflow stage skill; do not perform a stage by itself.
---

# Workflow Artifacts

Before reading or writing a governed workflow artifact, read the project's active `artifact_contract` from `project.yaml` at its artifact-repository root, then read that complete contract and every earlier version it extends. The contract is the authoritative storage and metadata schema for new runs in that repository. An existing run remains governed by its recorded contract version; never retroactively convert it because the project default changed. If an older run lacks an explicit version, preserve its original contract and seek clarification before applying new rules to it. Do not infer approval or authority from a filename alone.

The artifact repository is separate from the product-code repository: `~/Developer/AI-Workflows/<Project>/` is one Git repository per project. Use the technology and workflow identifiers recorded in the workflow manifest to locate a run. Never select the globally newest artifact when project, technology, feature, or run differs.

Each agent writes only its assigned folder within a run. The orchestrator owns the manifest, validation records, human approval records, and run report. Keep human decisions, agent recommendations, assumptions, and unknowns distinct. Do not create an approval record without an actual human decision.

For a run governed by Contract v1.1 or later, the orchestrator owns the single artifact-repository PR for that run. The execution coordinator owns the product PR for each changed product repository in delivery mode; evaluation has no product PR. Read and record verified PR URLs, repository identities, base and head branches, commits, and states; never infer any of them. Contract v1.2 adds fixed workflow mode, a second delivery gate, forward-only stages, and an event journal; read its full text before handling a v1.2 run.

When the artifact repository or required contract is missing, stop and request the missing project setup; do not silently fall back to the product repository or an old `Developer/<Project>/<Stage>/` path.
