---
name: atra-service-platform
description: Build or change ATRA TypeScript backend services and workspace packages while following the repository's established ESM, composition, and boundary conventions. Use for ATRA service implementation, not for independent architecture approval.
---

# Atra Service Platform

Use this skill for implementation or maintenance in the ATRA backend monorepo. It supplements the governing workflow stage; it does not decide product scope, architecture, or release approval.

## Established platform shape

- Treat the repository as a TypeScript, Node ESM workspace. Inspect the target app/package configuration before editing: the current services have different local compiler and package settings, so do not silently standardise them as part of feature work.
- Preserve explicit `.js` local import specifiers and `import type` separation where used. Keep domain types at the closest appropriate boundary.
- Keep the composition root responsible for wiring concrete dependencies. Route factories assemble Express routers; controllers translate HTTP concerns; services own use-case orchestration; repositories or the database package own persistence access.
- For market-data work, the equivalent boundary is adapter → cache/service → REST or WebSocket transport. Keep external-provider protocol details out of transport and domain services.
- Use dependency injection or factories at side-effect boundaries (database, HTTP client, WebSocket) when it improves testability and follows the surrounding module.

## Workspace boundaries

- `packages/database` is the shared persistence boundary. Do not duplicate schema types or create another database client abstraction inside a service without an explicit design decision.
- Several named apps and packages are placeholders. Treat their READMEs as intended direction, not an implementation contract; do not build unrequested scope from them.
- Keep service configuration local until a shared configuration contract is deliberately introduced. Existing services load environment configuration differently.

## Before completing work

Confirm the changed module still has a clear owner, its public API is documented when affected, and the selected test level follows existing Vitest conventions. Raise a decision when the work would change a cross-service contract or requires platform standardisation.
