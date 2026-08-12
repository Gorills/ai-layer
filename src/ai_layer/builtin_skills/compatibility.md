---
slug: compatibility
description: Compatibility discipline for API, schema, configuration and dependency evolution across old data, clients and mixed deployed versions.
kind: capability
keywords:
- compatibility
- backward compatibility
- upgrade
- deprecation
- mixed version
- schema evolution
- rollout
- rollback
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Compatibility and Evolution Skill

## Apply when

Use when changing an externally consumed API, persisted format, database schema, event, configuration key, dependency major version or any behavior that old clients/data/processes may encounter during rollout or rollback.

## Core contract

- Define the compatibility window explicitly: which old clients, data, workers or deployed versions must coexist and for how long.

- Backward compatibility is semantic, not only syntactic. Same field names with changed meaning, defaults, ordering or error behavior can still break consumers.

- Prefer expand-migrate-contract for durable schemas and additive protocol evolution for independently deployed consumers.

- Readers should usually become tolerant before writers emit the new representation; destructive contraction comes last.

- Rollback means old code must survive any data/config written by the new version for the promised rollback window.

- Deprecation requires observable usage, communication/ownership and a removal condition; a comment marked deprecated is not a migration plan.

- Version transforms at boundaries and normalize internally; avoid branching old/new semantics throughout business logic.

- Test representative old state and mixed versions. Fresh installations prove almost nothing about upgrade compatibility.

- Dependency upgrades are product changes when behavior, transitive contracts, serialization or operational defaults can change.

- Do not maintain compatibility forever by default; every compatibility layer has complexity cost and should have an exit criterion.

## Evidence to inspect

- Current and historical API/event/schema/config versions and all known consumers.

- Migration history, persisted records from older versions and serialized/cache/object-store formats.

- Deployment topology and whether old/new processes run concurrently during rolling rollout.

- Rollback process and maximum time a previous release may be restored.

- Deprecation telemetry, logs or consumer inventory showing who still uses legacy behavior.

- Dependency lock diff, upstream migration guide/release notes and local wrappers/tests.

## Decision rules

- If old and new versions can overlap, every changed shared datastore/message must be readable safely by both during overlap.

- If a field is being renamed, add/read both or provide a compatibility alias before removing the old name.

- If semantics change incompatibly, prefer a new version/operation/event name rather than silently reusing the old contract.

- If a database column/type changes, use additive schema plus backfill and delayed contraction when rolling deployments/rollback matter.

- If an event consumer is independently deployed, assume consumers update later than producers unless coordinated deployment is guaranteed.

- If a dependency major upgrade changes behavior, isolate it behind existing adapters and add focused contract tests before broad refactors.

- If compatibility has no known consumer and no required window, do not add speculative shims solely from fear.

- If a shim is introduced, record the exact condition that permits deletion and how to detect remaining legacy usage.

## Workflow

1. Inventory consumers, persisted representations and deployment/rollback overlap for the changed contract.

2. Write the old and desired contract side by side, including defaults, errors, ordering and side effects.

3. Choose an evolution sequence where each intermediate state is valid for the required compatibility window.

4. Implement tolerant readers/adapters first and add telemetry for legacy representation usage where useful.

5. Deploy/add new writers only after compatibility readers are available.

6. Backfill or migrate durable data in restartable bounded batches when necessary.

7. Remove old writers/readers/schema only after usage evidence and rollback window permit contraction.

8. Run upgrade, mixed-version and rollback-oriented tests before declaring the transition complete.

## Implementation patterns

- Expand-migrate-contract: add compatible shape, migrate usage/data, then remove old shape in a later safe step.

- Dual-read/single-write can be safer than dual-write when transitioning representations; dual-write requires reconciliation semantics.

- Protocol versioning should reflect semantic incompatibility, not every additive field.

- Compatibility adapters belong at boundaries so the internal model can remain canonical.

- Feature flags can decouple deployment from activation, but require default, ownership, cleanup and mixed-state testing.

- Data backfills should be idempotent/restartable and observable with progress/error counts.

- Dependency upgrade tests should pin the important behavior the application relies on, not mirror upstream implementation.

- Deprecation warnings/metrics should identify the legacy contract without exposing sensitive caller data.

## Failure modes

- Schema contraction first: old process fails during rolling deployment. Expand and delay destructive migration.

- Silent semantic break: response field exists but units/defaults change. Version or adapt semantics explicitly.

- Dual-write drift: two representations diverge after partial failures. Define authority/reconciliation or avoid dual-write.

- Rollback trap: new code writes data old code cannot parse. Test reverse compatibility for the rollback window.

- Forever shim: compatibility branch remains with no usage evidence or removal trigger. Add lifecycle ownership.

- Fresh-only test: CI creates empty database and misses upgrade behavior. Seed representative old state.

- Unscoped dependency bump: many packages update and regressions cannot be attributed. Bound and review the lock diff.

- Version checks everywhere: business code forks on old/new representations. Normalize at the boundary.

## Verification

- Run tests with representative old payloads/data/config and the new implementation.

- Where feasible, run old reader against new-writer output for the promised rollback/mixed-version window.

- Validate rolling deployment order and schema/event compatibility across process versions.

- Measure or inspect legacy usage before deleting compatibility behavior.

- Run migration/backfill on nontrivial representative data and verify idempotent restart.

- Review dependency release/migration notes for detected pinned versions and run local contract tests.

- Search for legacy names/branches after contraction to ensure no hidden writer/reader remains.

- Document any intentionally unsupported old version and confirm operators/users have a clear upgrade path.

## Completion criteria

- The required compatibility window and supported old/new states are explicit.

- Every rollout intermediate state and rollback path is safe for the deployment topology.

- Old data/clients are tested, not assumed.

- Compatibility logic is localized and has a removal condition.

- Destructive contraction occurs only after telemetry/evidence and rollback constraints allow it.

- Dependency/protocol/schema changes have focused contract evidence beyond a clean-install test.

## Related skills and escalation

- Use `api-contracts`, `database-migrations` and `data-consistency` for concrete evolution mechanics.

- Use `source-first` for version-specific dependency behavior and migration guides.

- Use `external-integrations` when a third party controls upgrade timing.

- Escalate when consumer inventory or rollback requirements are unknown for an irreversible contract change.
