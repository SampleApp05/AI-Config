---
name: atra-market-streaming
description: Build or document ATRA market-data ingestion, caching, REST access, and WebSocket streaming. Use for exchange adapters and realtime subscription behaviour, not for generic frontend WebSocket work.
---

# Atra Market Streaming

Apply this skill to `apps/market-service` and to services that consume its market-data contract.

## Boundary model

- Treat an exchange as an external adapter. Normalize provider REST and WebSocket payloads into ATRA market types before they cross into services or transports.
- Keep provider connection/reconnect and subscribe/unsubscribe protocol in the adapter. Keep cache policy, subscription state, and fan-out in services. Keep request parsing and client message handling in REST/WebSocket transports.
- The current cache supports fresh reads, stale-while-revalidate, and in-flight request de-duplication. Preserve the intended freshness and failure semantics when altering it.
- The stream manager tracks client subscriptions and upstream subscriptions separately, using reference counts to avoid duplicate upstream subscriptions and to release them when the last client leaves.

## Contracts and operations

Normalize symbols at the documented boundary, use typed client message unions for WebSocket commands, and document message direction plus lifecycle effects for every protocol change.

Do not make a provider-specific field part of an ATRA public contract without an explicit compatibility decision. For changes involving reconnect, cache expiry, fan-out, or upstream failure, state the observable client behaviour and test the relevant transition.
