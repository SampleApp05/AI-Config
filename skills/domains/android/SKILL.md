---
name: android
description: Apply Android application expertise when an assigned workflow stage concerns Android clients. Use with a governing stage skill; do not independently expand scope or stage authority.
---

# Android

Use this skill for an Android client concern within an active workflow stage. Establish the existing app shape before recommending or editing: modules, Kotlin/Java mix, UI toolkit, navigation/state pattern, minimum and target SDKs, build variants, and release pipeline. Do not introduce a framework, architecture pattern, or dependency as incidental feature work.

## Product and platform judgement

- Trace the affected user flow across UI state, lifecycle, ViewModel or equivalent state owner, repository/service boundary, and persistence. Define loading, empty, error, retry, process-death, rotation, and navigation-back behaviour where applicable.
- Check Android version and device capability behaviour for permissions, background execution, notifications, deep links, storage, network availability, and accessibility. Treat a permission denial or unavailable capability as a normal state, not an exceptional crash path.
- Preserve responsive layouts, keyboard and screen-reader operation, semantic labels, dynamic text sizing, contrast, and touch targets. Do not claim accessibility compliance without checking the affected interaction.
- Keep API calls, credentials, and sensitive data out of UI state, logs, screenshots, and insecure local storage. Use the security skill when the change affects identity, payments, device trust, or sensitive data.

## Delivery evidence

Prefer existing unit, UI, and device-test conventions. Test state transitions and platform-specific behaviour at the smallest useful level; state device/API coverage gaps explicitly. For a release-sensitive change, identify compatibility impact, feature-flag or staged-rollout needs, crash/ANR signals, and rollback feasibility.

Follow the governing workflow artifact and stage skill. Do not take ownership of routing, approval, or adjacent workflow stages.
