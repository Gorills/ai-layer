# ADR 0008 — Durable workflow authority before Epics

**Status:** accepted for v0.10.0 pre-Epics hardening.

## Context

The v0.9.2 Task Engine persisted Task/Stage rows in PostgreSQL but relied on filesystem JSON snapshots for baseline/stage recovery, and critical mutations were primarily serialized by a machine-local filesystem lock. That is insufficient for crash recovery, more than one process, or a future remote command boundary. Durable events also lacked actor/correlation attribution, and verification execution had no explicit capability/executor seam.

## Decision

### Canonical workflow state

PostgreSQL is authoritative for Task/Stage state and for the identity metadata needed to compare repository states. `repository_snapshots` stores immutable path/hash/stat metadata only; source file contents are not copied into PostgreSQL. `Task.baseline_snapshot_id` and `TaskStage.start_snapshot_id` reference the canonical snapshot. Existing task JSON files are disposable materialized projections.

New Task/Stage state and its snapshot reference are written in one database transaction. Filesystem materialization happens only after commit and is best-effort. Legacy in-flight rows keep nullable snapshot references so an existing valid JSON snapshot can be checked against its stored digest and promoted. If that legacy evidence is already missing or inconsistent, recovery fails closed rather than inventing provenance.

`WorkflowSnapshotStore` is the strategic persistence port. The initial adapter is SQLAlchemy/PostgreSQL-backed. This intentionally does not introduce object/blob storage or a message broker.

### Concurrency and stale writes

PostgreSQL owns critical concurrency invariants:

- one open (`active`/`blocked`) Task per Project — partial unique index;
- one active TaskStage per Task — partial unique index;
- project/task mutations — row-level `FOR UPDATE` locking;
- remote-style stale command protection — monotonic `Task.version` with optional `expected_version` checks.

Filesystem locks remain a local optimization and protection around project-local materializations. Correctness must still hold when those locks are absent.

### Command and event backbone

A canonical idempotent command primitive stores a unique `command_id`, request hash, result and actor/correlation metadata. Mutation + completed receipt are intended to share the caller-owned transaction. A handler used by this boundary must not commit independently. Existing local Task helper APIs are not retroactively advertised as remote-safe commands; a future remote transport must enter through this transactional application command boundary.

`RuntimeEvent` is the single durable event journal. Events now carry schema version, correlation/causation, actor, interface and command identity. Business state and events written by Task transitions share the same SQLAlchemy transaction. Consumer checkpoints provide a minimal replay/idempotent-consumer contract; Kafka/NATS/etc. are deliberately absent.

### Security and approvals

`Actor`, `Capability`, `PolicyDecision` and `ApprovalRequest` are runtime/application concepts. Authorization belongs in the application layer, not CLI/MCP/FastAPI/dashboard adapters. The current service remains trusted-local and loopback-only. No unauthenticated remote surface is added.

Verification remains a trusted-local subprocess and is explicitly **not** a sandbox. It requires `shell.execute` capability at the application boundary and is invoked through a replaceable `VerificationExecutor` port so a future hardened executor can replace it without changing Task semantics.

### Workflow extension and Epics

The four current stages are registered through `StageDefinition`: role, read-only/mutating classification, completion contract, required capabilities, outcomes and possible successors are centrally declared. This is intentionally smaller than a generic BPMN/workflow engine.

Epic Layer may plan/depend/aggregate Tasks. It may not own Task worker leases, Task repository snapshots, Task verification/review/fix/remediation lifecycle, or a parallel Task state machine/event truth. Static architecture checks protect that boundary before Epic code exists.

### Execution attempts

No separate `Execution` entity is added in this release. A failed/lost attempt is already retained as an invalid/completed TaskStage row and recovery creates a fresh ordinal TaskStage, preserving worker/model/timing/result history. Introduce a separate Execution entity only if future requirements need multiple concrete attempts *within the same logical stage identity*; adding it now would duplicate current persistence without proven need.

## Rejected alternatives

- PostgreSQL BLOB storage of repository contents — unnecessary and increases sensitive-data/storage cost.
- Filesystem locks as the concurrency authority — not cross-process/database authoritative.
- A second JSON/dashboard/remote state store — creates split-brain state.
- Kafka/NATS/Redis Streams — no current distributed consumer requirement.
- Big-bang TaskRepository/UnitOfWork rewrite — current ORM-centric Task Engine would incur high migration risk. Only strategic replaceable boundaries are extracted now.
- Full container sandbox — outside trusted-local scope; the current trust model is stated explicitly and the executor seam is prepared.
