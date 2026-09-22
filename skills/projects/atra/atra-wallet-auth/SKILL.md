---
name: atra-wallet-auth
description: Implement or document ATRA wallet-based authentication, authorisation, sessions, roles, recovery, and chain configuration. Use alongside security judgment when a change affects trust or access control.
---

# Atra Wallet Auth

Apply this skill to work in `apps/auth-service` that changes identity, access, wallet roles, recovery, session behaviour, or supported EVM chains.

## Domain model to preserve

- Authentication is challenge/signature based: a wallet signs a purpose-specific EIP-191 message. It is not a password flow.
- Challenge nonces are persisted, purpose-bound, time-limited, and single-use. Treat nonce issuance, verification, and consumption as one security-sensitive flow.
- Access JWTs coexist with persisted opaque refresh sessions. A protected request must remain tied to a live, unrevoked session as well as a valid token.
- A wallet can hold an account-specific role (`OWNER`, `AUTH`, `STANDARD`, or `RECOVERY`). Role mutation and owner recovery are domain operations, not generic profile updates.
- Sensitive operations write audit records. Preserve the actor/account context and action meaning when extending those flows.
- Chain metadata is centrally resolved by `ChainService`; RPC, WebSocket, and contract endpoints are environment-injected rather than static source configuration.

## Change workflow

Trace the full operation before changing it: route/controller inputs, middleware context, service behaviour, database records, error contract, audit effect, and client-visible documentation. Use a transaction when one user-visible operation must create or change multiple persistent records atomically.

Do not introduce a new signing format, JWT claim, role meaning, recovery authority, token lifetime policy, or trust boundary as an incidental implementation choice. Surface it as a decision and involve the governing security workflow when appropriate.

Keep public versus protected endpoints explicit. Do not document a security property as implemented unless it is evidenced by the current route, middleware, and service behaviour.
