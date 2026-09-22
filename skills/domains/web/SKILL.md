---
name: web
description: Apply browser-based application expertise when an assigned workflow stage concerns web clients. Use with a governing stage skill; do not independently expand scope or stage authority.
---

# Web

Use this skill for browser-delivered client features within an active workflow stage. First establish the existing routing, rendering, state, design-system, API-client, authentication, build, and test conventions. Do not replace the framework, styling approach, or state architecture as incidental feature work.

## Product and browser judgement

- Trace the complete user flow, including initial, loading, empty, success, validation, authorization, error, retry, navigation, refresh, and back-button states. Keep client state and server truth distinct; identify cache invalidation and stale-data behaviour when data changes.
- Preserve semantic HTML, keyboard operation, focus management, labels, errors announced to assistive technology, contrast, zoom and reflow, touch targets, and responsive layouts. Do not call an interface accessible without validating the affected flow.
- Evaluate browser compatibility, network loss and recovery, cookies/session behaviour, client-side storage, caching, bundle impact, rendering performance, and observability in the existing application context.
- Use the security skill for auth, personal data, cross-origin, untrusted content, payment, or sensitive client-storage changes. Never rely on client-side checks as the sole authorization control.

## Delivery evidence

Use the project’s established unit, component, integration, and end-to-end test layers. Verify the user-visible result and meaningful failure state at the smallest sufficient level; document unsupported-browser, assistive-technology, or performance coverage gaps honestly. Update API-facing documentation when browser-observable contracts change.

Follow the governing workflow artifact and stage skill. Preserve established design systems and project conventions; do not take ownership of routing, approval, or adjacent workflow stages.
