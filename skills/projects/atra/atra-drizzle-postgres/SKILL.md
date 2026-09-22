---
name: atra-drizzle-postgres
description: Change or document ATRA PostgreSQL persistence built with Drizzle ORM and postgres.js, including schemas, migrations, repositories, and transaction boundaries. Use with the governing database stage when one exists.
---

# Atra Drizzle Postgres

Use this skill for work touching `packages/database` or ATRA service persistence.

## Repository conventions

- The shared Drizzle table definitions in `packages/database/src/schema` are the schema source of truth. Export table and inferred types through its barrel rather than copying shapes into consuming services.
- The database package exposes an environment-agnostic `createDb(connectionString)` factory. Services provide their own environment loading and connection string at their composition boundary.
- Model role, nonce-purpose, session, and audit semantics with the existing typed schema rather than loose string conventions.
- Put focused data access behind an existing repository when one owns that aggregate. Services may orchestrate multi-table use cases when that is the established local pattern.

## Schema and data changes

For a material schema change, identify the affected services, existing data compatibility, constraints/indexes, migration and rollback approach, and documentation impact before editing. Generate migrations through the package's Drizzle tooling; never hand-edit generated output unless the change explicitly requires it and the result is reviewed as migration code.

Use a transaction when an operation must preserve an invariant across multiple rows or tables—for example account provisioning, role changes, or recovery. Do not casually combine unrelated persistence changes with a feature request.

Keep credentials out of committed source and examples. Treat test database setup, production migration execution, and destructive data operations as separately authorised actions.
