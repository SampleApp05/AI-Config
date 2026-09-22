---
name: atra-feature-replay
description: Reconstruct an ATRA feature's intended and implemented state from commits, source, tests, configuration, and documentation. Use for evidence-based workflow replay, not for code review or unsolicited remediation.
---

# Atra Feature Replay

Use this skill when the team wants to revisit one bounded ATRA feature—such as account creation, wallet linking, market subscriptions, or multi-chain support—and understand what was meant to be delivered and what evidence exists today.

## Scope and evidence

Start with a named feature or commit range. Do not widen the replay to the whole repository unless explicitly asked. Gather only relevant commit messages/diffs, source paths, tests, environment configuration, and documentation.

Keep these categories separate:

- **Stated intent:** what commit messages, approved artifacts, or contemporary documentation say the feature was for.
- **Observed implementation:** behaviours evidenced by current source and tests.
- **Planned or deferred work:** placeholder packages, TODOs, or future-oriented documentation.
- **Unknowns:** intent or runtime behaviour that cannot be established from the evidence.

## Output

Produce a concise evidence pack with feature boundary, chronology, observable behaviour, public contract/configuration impact, tests and documentation evidence, open questions, and traceable source/commit references. State discrepancies neutrally; do not label them defects or recommend code changes unless the user separately requests assessment or remediation.

The replay is read-only by default. Creating workflow artifacts, changing documentation, evaluating stack suitability, or opening a code review requires a separate explicit request.
