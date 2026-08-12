---
slug: database-migrations
description: Production-safe schema and data migration discipline for expand-backfill-contract, locking, mixed versions, rollback and restartable execution.
kind: capability
keywords:
- migration
- schema migration
- backfill
- zero downtime
- rollback
- alembic
- django migration
- locking
- expand contract
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Database Migration Skill

## Apply when

Use for any deployed database schema, constraint, index, type or durable-data transformation. Apply even when ORM tooling can auto-generate the migration: generated DDL does not decide rollout compatibility, locks, backfill safety or rollback semantics.

## Core contract

- Design the rollout sequence before writing migration syntax. Schema compatibility with old/new application versions is the primary constraint during rolling deploys.

- Prefer expand → migrate/backfill → switch readers/writers → contract for destructive or semantic changes.

- Separate large data backfills from short schema changes when one transaction would lock tables, fill logs or make restart impossible.

- Make backfills deterministic, bounded, idempotent/restartable and observable; record progress using stable keys, not fragile offsets.

- Adding NOT NULL/unique/foreign-key constraints to existing data requires auditing/backfilling violations before fail-closed enforcement.

- Index creation strategy must account for table size, locking and supported database features; do not assume local tiny-table behavior represents production.

- Rollback includes data compatibility. A down migration that drops newly written information may be less safe than a forward fix.

- Never edit applied historical migrations merely to make a fresh database look clean unless the project's migration policy explicitly permits squashing/rebasing.

- Test migration from representative old state/data and mixed-version application expectations, not only empty schema.

- Have an operator recovery plan for interrupted backfills and partially completed deploys.

## Evidence to inspect

- Complete migration history around affected objects and current production-like schema state.

- Row counts/data distribution/null/duplicate violations relevant to new constraints.

- Deployment strategy: rolling versus stop-the-world, number of old/new app versions in overlap and rollback window.

- Database engine/version and DDL locking/concurrent-index capabilities from authoritative docs.

- Application read/write paths for old and new columns/representations.

- Existing migration/backfill framework, timeout settings and operational progress/metrics.

## Decision rules

- If a column rename must support rolling versions, add new column/read compatibility and backfill rather than an immediate destructive rename unless DB/app semantics prove it safe.

- If a new required field has existing rows, add nullable/default-compatible shape, deploy writers, backfill, validate, then enforce requiredness.

- If uniqueness is added, detect/reconcile duplicates before creating the constraint and define conflict semantics.

- If a backfill is large, run bounded batches outside one migration transaction when project operations support that model.

- If old code cannot read new representation, do not emit it until old readers are upgraded or compatibility is added.

- If rollback would destroy data or be operationally riskier, document forward-only recovery instead of pretending reversible DDL is safe.

- If historical migration files are already deployed, add a new corrective migration rather than rewriting history.

- If the database supports online/concurrent operations, verify exact version/tool transactional restrictions before using them.

## Workflow

1. State old schema/data contract, desired contract, mixed-version window and rollback requirement.

2. Inspect real/representative data for nulls, duplicates, invalid enums, oversized values and other blockers.

3. Design expand/backfill/switch/contract phases with independently deployable checkpoints.

4. Write the smallest schema expansion and make old application behavior remain valid.

5. Deploy compatible readers/writers, then run restartable observable backfill in bounded batches.

6. Validate backfill completeness/invariants before enabling the new constraint or removing the old representation.

7. Contract only after old code/usage and rollback window are gone.

8. Test upgrade, interruption/restart and operational rollback/forward-fix scenarios.

## Implementation patterns

- Dual-read with a canonical preference can bridge field migrations; keep the compatibility code at the persistence/boundary layer and remove it after cutover.

- Dual-write requires handling partial write failure and consistency; when one DB transaction covers both columns it is simpler, otherwise prefer one authoritative write plus backfill.

- Backfill by stable primary-key ranges/cursors and commit each bounded batch; record counts/errors and make rerun safe.

- Validate constraints before enforcing where the engine/tool supports staged validation, after verifying version-specific semantics.

- For large indexes, use the database's online/concurrent mechanism only with correct migration transaction settings.

- Enum/type changes should consider old binaries and rollback readers, not only the new ORM model.

- Data migrations should use historical schema/model state where the migration framework requires it rather than importing current application models blindly.

- Feature flags can gate switching readers/writers but need cleanup and default/mixed-state tests.

## Failure modes

- Auto-generated confidence: ORM produced migration so it is assumed safe. Review DDL, locks, existing data and deploy order.

- NOT NULL first: existing rows or old writers break. Expand/backfill/switch/enforce.

- Huge one-shot backfill: locks/log volume/timeouts make migration unrecoverable. Batch and checkpoint.

- Offset batching: updates/deletes cause skips/repeats. Use stable key ranges/cursors and idempotence.

- Edited history: deployed environments and fresh installs diverge. Append corrective migration.

- Rollback fiction: down migration succeeds syntactically but drops data new code wrote. Define real recovery.

- Concurrent-index misuse: command runs inside forbidden transaction or unsupported version. Source-first verify DB/tool semantics.

- Constraint without cleanup: production duplicate/null data makes deploy fail mid-flight. Audit before enforcement.

## Verification

- Apply migrations from a representative pre-change schema/data snapshot, not only an empty database.

- Run backfill twice/interrupted and confirm idempotent completion with correct counts.

- Verify old and new application read/write expectations during the planned mixed-version phase.

- Inspect locks/timing/query plan or dry-run DDL behavior on production-scale-like data where material.

- Validate constraints/indexes after backfill using direct database inspection.

- Test deployment rollback/forward-fix semantics with data written by the new version.

- Run migration framework consistency checks and full canonical tests.

- Ensure historical migrations remain unchanged unless an explicitly supported squash/rebase operation is being performed.

## Completion criteria

- Rollout phases and compatibility window are explicit and independently safe.

- Existing data is audited/backfilled before stricter constraints depend on it.

- Large data work is bounded, restartable and observable.

- Old/new application versions can coexist for the deployment plan.

- Rollback or forward-recovery behavior is realistic and data-safe.

- Representative upgrade and interruption evidence exists.

## Related skills and escalation

- Use `database` for schema/query semantics, `compatibility` for mixed-version reasoning and `data-consistency` for dual representations.

- Use stack-specific migration sections such as Django/Laravel/Alembic patterns for tooling details.

- Use `source-first` for database-version-specific DDL locking and online migration features.

- Escalate before destructive production migration when data cardinality/rollback topology is unknown.
