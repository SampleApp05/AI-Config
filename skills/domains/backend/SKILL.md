---
name: backend
description: Apply server-side service and API expertise when an assigned workflow stage concerns backend systems. Use with a governing stage skill; do not independently expand scope or stage authority.
---

# Backend

Use this skill for server-side services, jobs, and public or internal API concerns within an active workflow stage. First establish the service boundary, callers, public contract, configuration model, persistence ownership, and current operational conventions. Do not standardise unrelated services or choose a replacement stack as incidental feature work.

## System judgement

- Preserve externally observable contract behaviour: authentication and authorization, validation, status/error shape, pagination, idempotency, compatibility, side effects, and versioning where relevant. Escalate a new public contract or breaking change rather than silently introducing it.
- Make timeouts, retries, cancellation, concurrency, duplicate delivery, partial failure, and recovery behaviour explicit. Use idempotency and transactions when an operation can be repeated or span durable state; do not promise exactly-once behaviour without evidence.
- Keep transport, use-case orchestration, domain logic, and persistence or provider access at the repository's established boundaries. Avoid leaking provider-specific or database-specific details into public interfaces.
- Treat configuration, secrets, sensitive logging, rate limits, resource limits, health/readiness checks, metrics, tracing, and audit events as part of the service behaviour when the change affects them.

## Delivery evidence

Test at the lowest level that proves the requirement, then add contract or integration coverage for boundary behaviour and meaningful failure modes. Report command results and operational coverage gaps. Coordinate with database, integration, security, infrastructure, or API-documentation skills when those boundaries materially change.

Follow the governing workflow artifact and stage skill. State assumptions and unknowns instead of inventing project conventions; do not take ownership of routing, approval, or adjacent workflow stages.
