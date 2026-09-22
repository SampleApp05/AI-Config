---
name: infrastructure
description: Apply deployment, runtime, reliability, and platform expertise when an assigned workflow stage concerns infrastructure. Use with a governing stage skill; do not independently expand scope or stage authority.
---

# Infrastructure

Use this skill for runtime environments, deployment, hosting, networking, observability, and platform operations within an active workflow stage. Start from the existing environment model, infrastructure-as-code or manual process, ownership, service dependencies, and incident/release practices. Do not move providers or redesign platform topology unless that is the approved concern.

## Operational judgement

- Define environment-specific configuration, identity and access boundaries, network exposure, secret handling, and least-privilege implications. Never place credentials or generated secret values in artifacts, source, logs, or examples.
- Evaluate deployment order, health/readiness behaviour, graceful shutdown, backward compatibility, rollout strategy, rollback trigger, and failure containment. Prefer a reversible, observable change when practical; state when it is not reversible.
- Consider capacity, rate limits, autoscaling or fixed limits, cost drivers, dependency availability, backups/disaster recovery, and relevant service-level indicators. Do not use unmeasured capacity claims as evidence.
- Ensure the change has actionable logs, metrics, traces or events, alert ownership, and a way to detect both rollout failure and degraded steady state.

## Delivery evidence

Validate through the smallest safe environment and record the environment, plan/apply outcome, health evidence, and rollback result or rationale. Treat live deployment, production configuration changes, and destructive infrastructure operations as separately authorised actions.

Follow the governing workflow artifact and stage skill. Do not take ownership of routing, approval, or adjacent workflow stages.
