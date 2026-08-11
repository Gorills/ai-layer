---
slug: database
description: Database query, transaction, constraint, and operational safety discipline.
kind: domain
keywords:
- database
- sql
- postgres
- sqlalchemy
- query
- index
- transaction
- constraint
- table
- schema
- repository
- orm
- connection
- pool
- база
- запрос
- индекс
- транзакц
---
# Database Skill

## Apply when
Queries, transactions, schema invariants, connection lifecycle, indexes, ORM behavior, or persistent data are affected.

## Mandatory rules
- Put durable invariants in database constraints when the database can enforce them safely.
- Parameterize queries; authorize and bound user-driven reads.
- Keep transaction, connection, timeout, cancellation, and retry lifecycles explicit for the runtime.
- Choose indexes from actual access patterns; account for write/storage/migration cost.
- Do not assume development data volume represents production behavior.

## Decision rules
- Use one transaction when several writes must succeed or fail as one invariant-preserving unit.
- Do not retry integrity or serialization failures blindly; first determine whether the operation is safe and what conflict semantics mean.
- Prefer a query-shape fix before adding caching to hide an inefficient access pattern.

## Failure modes
N+1 access, unbounded scans, connection leaks, transactions held during unrelated I/O, application-only uniqueness, accidental full-table locks, and indexes added without a query reason.

## Quality gates
- Nullability/default/unique/FK/check semantics are intentional.
- Query count/shape is reasonable for the hot path.
- Concurrency-sensitive writes have deterministic conflict behavior.
- Real integration coverage is used for persistence behavior that mocks cannot prove.
