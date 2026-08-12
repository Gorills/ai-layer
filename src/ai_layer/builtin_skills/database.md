---
slug: database
description: Relational database discipline for schema design, constraints, indexes, queries, transactions, locking, performance and data ownership.
kind: domain
keywords:
- database
- sql
- postgres
- schema
- index
- query plan
- transaction
- constraint
- locking
- normalization
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Database Engineering Skill

## Apply when

Use when adding/changing tables, queries, relationships, indexes, transaction behavior, high-cardinality data access or persistence architecture. Combine with the migration skill for deployed schema changes.

## Core contract

- Model durable business invariants explicitly with types, nullability, keys and constraints; the database is an active correctness layer, not a passive object store.

- Choose normalization/denormalization based on ownership and measured read/write needs. Derived duplicated data needs a synchronization/rebuild story.

- Index for real query predicates/order/join patterns and cardinality; every index has write/storage/maintenance cost.

- Inspect query plans for material paths. ORM syntax can hide full scans, N+1 behavior and poor join strategies.

- Keep transactions scoped to one coherent unit of work and avoid remote network calls while holding database locks.

- Understand concurrency at the SQL level: isolation, locks, unique conflicts and atomic updates; process-local mutexes do not protect multi-process deployments.

- Use deterministic pagination/order for large sets and avoid unbounded loads.

- Schema/data ownership should align with capability ownership; direct cross-module writes make invariants difficult to enforce.

- Treat deletion, retention, cascading and archival as product semantics, not incidental ORM defaults.

- Use migrations for all durable schema evolution and test representative existing data.

## Evidence to inspect

- Schema/models plus actual migrations, constraints and indexes in the database definition.

- Repository/query code and generated SQL for changed paths.

- Representative data cardinality/distribution and query plans.

- Transaction helpers, isolation settings, locks and retry-on-conflict logic.

- Foreign-key/cascade/soft-delete/retention behavior.

- Slow query metrics, production incidents or database diagnostics if performance is the concern.

## Decision rules

- If a rule must hold across all writers, encode it as a database constraint when the database can express it safely.

- If a query filters/orders on high-cardinality data frequently, evaluate a matching composite/partial index based on the exact predicate/order.

- If multiple rows must change atomically, use a transaction with explicit locking/atomic conditions appropriate to contention.

- If read-modify-write races, prefer `UPDATE ... WHERE ...`, version columns or locks over application sequencing.

- If an ORM relation causes per-row fetches, eager/prefetch intentionally or rewrite the query; do not hide N+1 with caching.

- If a column duplicates derived information, define who updates it and how it is backfilled/reconciled.

- If deletion may remove shared/auditable data, choose restrict/soft-delete/archive semantics explicitly rather than broad cascade.

- If a query result can grow, paginate/stream before production traffic dictates an emergency redesign.

## Workflow

1. Map entity ownership, invariants and access patterns before changing schema.

2. Inspect current schema/migrations and representative cardinalities; do not infer DB reality from model classes alone.

3. Design columns/constraints/relationships and anticipated query shapes together.

4. Choose indexes based on exact high-value predicates/order and verify with query plans.

5. Implement repository/query code with bounded result sets and explicit transaction ownership.

6. Add migration using expand/backfill/contract principles when deployed data exists.

7. Test constraints, concurrency and queries against the supported database engine.

8. Inspect query count/plan and rollback/data behavior before merge.

## Implementation patterns

- Surrogate primary keys plus separate natural/business unique constraints often preserve stable identity while enforcing domain uniqueness.

- Composite indexes should match leading filter/order access patterns; adding every column to every index is not optimization.

- Partial indexes can target frequent selective states when supported and query predicates align.

- Use CHECK constraints for durable local invariants and foreign keys for reference integrity unless architecture intentionally trades them off.

- Use `SELECT ... FOR UPDATE` only when serialization is required; optimistic concurrency avoids unnecessary lock contention for many edit flows.

- Use keyset pagination for large mutable ordered datasets where offset cost/instability matters.

- Batch/backfill queries should bound transaction size and progress deterministically.

- Store timestamps with unambiguous timezone semantics and keep application conversion at boundaries.

## Failure modes

- ORM-only schema: model validation exists but DB accepts invalid data from other writers. Add constraints.

- Index shotgun: many speculative indexes slow writes and bloat storage. Tie indexes to measured/query-plan need.

- N+1 invisibility: tests use three rows and query count explodes in production. Measure representative path.

- Transaction sprawl: controller wraps network calls and long computation. Narrow transaction to durable mutation.

- Unstable offset paging: users see duplicates/misses under concurrent changes. Use stable ordering/keyset where needed.

- Read-increment-write counter race: updates are lost. Use atomic increment/locking.

- Cascade surprise: deleting parent wipes auditable/shared children. Make lifecycle semantics explicit.

- SQLite substitute: Postgres-specific locking/constraint/query behavior is claimed from a different engine. Verify supported DB.

## Verification

- Run schema/constraint tests on the supported database, including invalid and concurrent cases.

- Inspect `EXPLAIN`/query plan for new or materially changed hot queries with representative cardinality.

- Measure query count for list/detail paths vulnerable to N+1.

- Run concurrent updates/inserts for uniqueness/version/locking invariants.

- Test pagination boundaries and stable ordering with duplicate sort values.

- Test delete/restore/archive/cascade behavior explicitly.

- Run migration upgrade against representative old data and verify resulting constraints/indexes.

- Check database connections/transactions close correctly on exceptions and retries.

## Completion criteria

- Schema expresses durable invariants and ownership clearly.

- Queries are bounded and have evidence for indexes/plans on material paths.

- Concurrency behavior is enforced at database/application boundary, not assumed.

- Transaction scopes exclude unnecessary external work.

- Deletion/retention lifecycle is explicit.

- Migration and real-engine verification cover existing data and failure cases.

## Related skills and escalation

- Use `database-migrations` for deployment-safe evolution and `data-consistency` for multi-system invariants.

- Use `backend` for use-case transaction ownership.

- Use framework skills for ORM idioms after database semantics are decided.

- Escalate when production cardinality or supported database engine cannot be reproduced for a high-risk performance/schema change.
