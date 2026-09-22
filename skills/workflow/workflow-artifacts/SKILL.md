---
name: workflow-artifacts
description: Apply the shared repository layout, artifact metadata, versioning, validation, and approval rules when creating or reading governed workflow artifacts. Use with a workflow stage skill; do not perform a stage by itself.
---

# Workflow Artifacts

Before reading or writing a governed workflow artifact, read the project's `ARTIFACT-CONTRACT-v1.md` at its artifact-repository root. The contract is the authoritative storage and metadata schema for that repository. If the repository uses a later approved contract version, read that version instead. Do not infer approval or authority from a filename alone.

The artifact repository is separate from the product-code repository: `~/Developer/AI-Workflows/<Project>/` is one Git repository per project. Use the technology and workflow identifiers recorded in the workflow manifest to locate a run. Never select the globally newest artifact when project, technology, feature, or run differs.

Each agent writes only its assigned folder within a run. The orchestrator owns the manifest, validation records, human approval records, and run report. Keep human decisions, agent recommendations, assumptions, and unknowns distinct. Do not create an approval record without an actual human decision.

For a run governed by Contract v1.1, the orchestrator also owns the single artifact-repository PR for that run. The execution coordinator owns the product PR for each changed product repository. Read and record the verified PR URL, repository identity, base and head branches, commit, and state; never infer any of them.

When the artifact repository or required contract is missing, stop and request the missing project setup; do not silently fall back to the product repository or an old `Developer/<Project>/<Stage>/` path.
