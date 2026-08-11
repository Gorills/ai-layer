---
slug: database-migrations
description: Live-data-safe database schema migration discipline.
kind: capability
keywords:
- migration
- schema
- alembic
- migrate
- backfill
- ddl
- rollback
- schema change
- column
- constraint
- index concurrently
- database upgrade
- миграц
- схема базы
- бэкфил
---
# Database Migrations Skill

## Apply when
Schema, constraints, indexes, data backfills, or database upgrade/downgrade behavior changes.

## Mandatory rules
- Inspect current schema, data assumptions, migration order, and deployment compatibility before writing DDL.
- Design for populated tables; do not assume empty development data.
- Separate expand/backfill/validate/contract steps when a one-step change can lock, fail, or break mixed-version deployments.
- Backfills are bounded, restartable/idempotent where needed, and observable.
- Never destroy or rewrite production data without explicit authorization and a recovery plan.

## Decision rules
- For a new required field on live data, prefer add-compatible → backfill → validate → enforce.
- Large indexes/constraints require awareness of database-specific lock/build semantics.
- Rollback must be realistic: if data transformation is irreversible, document forward-fix/recovery instead of pretending downgrade is safe.

## Failure modes
Long blocking DDL, non-null additions with no backfill, giant single transactions, migration code depending on current application models, and destructive downgrades that lose valid data.

## Quality gates
- Upgrade is tested against a representative existing schema/data state.
- Application compatibility during the deployment window is understood.
- Failure/retry/recovery behavior is documented for non-trivial migrations.
