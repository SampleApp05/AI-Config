---
name: database
description: Apply data modeling, persistence, migration, and integrity expertise when an assigned workflow stage concerns databases. Use with a governing stage skill; do not independently expand scope or stage authority.
---

# Database

Use this skill for persistent data, migrations, stores, and data-retention concerns within an active workflow stage. Identify the source of truth, owning service or aggregate, current schema/migration tooling, read and write paths, and real data compatibility before proposing a change. Do not conflate an application model with a storage model without checking existing boundaries.

## Data judgement

- Model invariants with constraints, types, relationships, uniqueness, and transaction boundaries appropriate to the datastore. Document the concurrency and isolation assumptions whenever concurrent writes can affect correctness.
- Assess schema changes against existing rows, old and new application versions, dependent readers, indexes/query plans, backfills, and rollout order. A migration needs forward safety; define rollback or recovery limits honestly when a rollback cannot restore lost meaning.
- Add or revise indexes from observed query paths, expected cardinality, and write cost—not intuition alone. Avoid hiding N+1 queries, unbounded scans, or lock-heavy migrations behind an ORM abstraction.
- Treat retention, deletion, export, encryption, access control, backups, restore testing, and auditability as explicit concerns when data sensitivity or lifecycle changes.

## Delivery evidence

Separate schema/code changes from production data operations unless both are explicitly authorized. Exercise migrations against representative existing data where feasible and test invariants, failure paths, and compatibility behaviour. Record data-loss, downtime, or backfill uncertainty as a risk rather than assuming a safe rollout.

Follow the governing workflow artifact and stage skill. Make rollout and reversibility concerns explicit; do not take ownership of routing, approval, or adjacent workflow stages.
