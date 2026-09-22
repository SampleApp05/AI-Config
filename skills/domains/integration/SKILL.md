---
name: integration
description: Apply third-party and cross-system integration expertise when an assigned workflow stage concerns external services or internal system boundaries. Use with a governing stage skill; do not independently expand scope or stage authority.
---

# Integration

Use this skill for third-party providers, asynchronous messaging, partner APIs, or internal system boundaries within an active workflow stage. Establish the system of record, contract owner, integration direction, credentials/scopes, data classification, current failure behaviour, and vendor or platform constraints before deciding on a change.

## Boundary judgement

- Specify request, response, event, or message ownership; field mapping; versioning; validation; and compatibility. Do not turn a provider-specific field or semantic into a public contract without an explicit decision.
- Make timeouts, retries, backoff, idempotency keys, ordering, deduplication, poison-message handling, replay, and partial-failure behaviour concrete. Delivery guarantees must be evidenced rather than labelled aspirationally.
- Isolate provider clients and protocol translation from domain rules and public transports. Keep secrets out of logs and artifacts, use the minimum necessary credentials, and coordinate with security where trust or personal data changes.
- Define observable integration health: correlation identifiers, success/failure metrics, diagnostic logs that exclude sensitive data, alert thresholds, and a manual recovery or reconciliation path when applicable.

## Delivery evidence

Use sandbox, contract, mock, or integration tests appropriate to the boundary; distinguish simulated from live-provider evidence. Document rate limits, quotas, maintenance windows, and vendor behaviour as constraints only when verified. Update the public contract or integration guide when observable behaviour changes.

Follow the governing workflow artifact and stage skill. Make external assumptions, dependencies, and fallback behaviour explicit; do not take ownership of routing, approval, or adjacent workflow stages.
