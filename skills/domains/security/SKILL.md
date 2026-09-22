---
name: security
description: Apply security and privacy expertise when an assigned workflow stage has trust, abuse, access-control, or data-protection concerns. Use with a governing stage skill; do not independently expand scope or approve risk.
---

# Security

Use this skill when a workflow concern materially affects trust boundaries, identities, authorization, sensitive data, external exposure, or abuse resistance. Identify assets, actors, entry points, trust transitions, intended controls, and evidence in the actual system before proposing mitigation. Do not turn a generic checklist into unsupported findings.

## Risk judgement

- Verify authentication, session/token lifecycle, authorization at the resource and operation level, tenancy isolation, privilege changes, and recovery/administrative paths. Distinguish authentication from authorization and enforcement from user-interface visibility.
- Follow data through collection, validation, serialization, storage, logs, analytics, exports, retention, and deletion. Minimize sensitive data and secrets; never expose them in artifacts, diagnostics, tests, or examples.
- Assess relevant input and transport risks at actual boundaries: injection, unsafe deserialization, path/file handling, request forgery, server-side request behaviour, browser exposure, replay, rate abuse, and denial of service. Apply only the threats that fit the system.
- Consider dependency provenance and updates, cryptographic use, secret rotation, audit trails, monitoring, and incident/recovery implications when the change touches them. Do not claim compliance, encryption, or protection properties without evidence.

## Delivery evidence

State severity, exploit preconditions, affected assets, evidence, residual risk, and mitigation verification in proportion to the stage. Use focused negative tests or review evidence where possible. Escalate material residual risk, new trust decisions, or policy exceptions for human authority; do not approve risk or alter workflow gates.

Follow the governing workflow artifact and stage skill. Do not take ownership of adjacent stages.
