---
name: workflow-api-documentation
description: Create or update accurate REST, event, and WebSocket contracts, service READMEs, and developer documentation from verified implementation and approved decisions. Use in any governed workflow; do not invent behaviour.
---

# Workflow API Documentation

Use this skill for developer-facing API contracts, integration guides, service READMEs, and endpoint or event documentation in any project or technology stack. Documentation is delivery work within the relevant requirement or execution unit; it does not create a separate workflow gate.

## Evidence and authority

Use the following order of authority: explicit current human decision; approved requirement or contract; implemented behaviour and its tests; then existing documentation. Treat examples, drafts, TODOs, and planned-service documents as intent rather than available behaviour.

If implementation and documentation disagree, identify the discrepancy and its evidence. Do not silently choose one or alter product behaviour merely to align prose. Request a decision on whether the required outcome is a documentation correction, a product change, or a versioned contract update.

## Contract content

For an HTTP endpoint, document purpose, method and path, authentication/authorisation, request fields, successful response, error status/payload, pagination or idempotency where applicable, and externally visible side effects.

For events, WebSockets, streams, or queues, document the connection or transport, authentication, message direction, message schema, subscription or acknowledgement semantics, ordering/delivery guarantees only when evidenced, and observable reconnect or malformed-message behaviour.

Use non-sensitive, realistic examples. Clearly distinguish required, optional, defaulted, and server-generated fields. Keep names, status codes, and payload shapes exact; do not standardise inconsistent interfaces without approval.

## README scope and verification

A service or component README should state ownership, dependencies, local configuration, run/test commands, public interfaces, and links to detailed contracts. Keep an overview README navigational rather than duplicating every contract.

Before delivery, cross-check every documented command, environment variable, endpoint, message field, security assertion, and link against source, tests, or the approved artifact. State verification gaps rather than filling them with plausible detail.
