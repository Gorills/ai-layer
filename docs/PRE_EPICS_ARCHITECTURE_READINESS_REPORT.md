# Pre-Epics Architecture Readiness Report — v0.10.0

## 1. Executive Summary

The audit started from the supplied v0.9.2 source archive and treated code, migrations, configuration and tests as the source of truth. The pre-existing project already had useful capability boundaries, an empty Epic namespace, structured Task lifecycle, runtime events, verification and architecture/release gates. However several requested pre-Epics assumptions were materially confirmed rather than merely theoretical.

The two most important P0 findings were real:

1. active Task recovery depended on filesystem `baseline.json` / `stage-*-start.json` snapshots even though Task/Stage lifecycle state lived in PostgreSQL;
2. critical sequential workflow invariants relied primarily on a local filesystem lock and were not enforced by PostgreSQL constraints/row locks.

Security/actor/capability and command-idempotency foundations were absent, runtime events lacked remote-control-grade attribution/correlation metadata, and stage extension rules were scattered rather than represented by a single declarative contract.

The implementation was hardened incrementally. PostgreSQL now owns canonical workflow snapshot identity, concurrency invariants, Task versioning, durable event attribution/checkpoints, approvals and idempotency receipts. Filesystem Task JSON is a disposable projection. Current stages are formalized by `StageDefinition`; the Epic boundary is statically protected from owning per-Task lifecycle primitives. Strategic snapshot/executor ports were extracted without rewriting the ORM-centric Task Engine or implementing Epics.

No source-level P0 architecture blocker remains identified by the repeat audit. Promotion is nevertheless withheld because mandatory real-PostgreSQL and official CPython-3.12 static quality evidence cannot be executed in this container.

## 2. Confirmed / Rejected Assumptions

| Assumption from the hardening brief | Audit result | Evidence in original archive | Implemented resolution |
|---|---|---|---|
| Filesystem snapshot loss can break active Task recovery | **CONFIRMED** | Task lifecycle/delegation/navigation/recovery loaded baseline/stage JSON from Task state directories | Added durable `RepositorySnapshot`; Task/Stage reference it transactionally; filesystem becomes best-effort materialization; legacy JSON is digest-validated/promotion-only |
| Filesystem lock is the authority for one-open-task / transition serialization | **CONFIRMED** | Mutating Task flows were guarded by `directory_lock` without DB partial uniqueness or authoritative row locking | Added Project/Task `FOR UPDATE`, partial unique indexes, Task version token and expected-version check; filesystem lock remains supplemental |
| Actor/Capability/Approval foundation exists | **NOT CONFIRMED** | No canonical runtime actor/capability/policy/approval model existed | Added `Actor`, `Capability`, `PolicyDecision`, `ApprovalRequest` and application policy service |
| Durable event backbone already exists | **PARTIALLY CONFIRMED** | `RuntimeEvent` existed and Task transitions emitted durable events | Kept the same journal; added correlation/causation/actor/interface/command/schema metadata and consumer checkpoints |
| Command idempotency exists | **NOT CONFIRMED** | No durable command receipt/idempotency-key boundary | Added `CommandReceipt` + PostgreSQL advisory command lock + request hash/result replay contract |
| New stage lifecycle is centrally extensible | **NOT CONFIRMED** | Stage semantics were distributed across constants/validation/navigation/transitions | Added `StageDefinition` registry; existing semantic handlers remain specialized, avoiding a generic BPMN engine |
| Epic subsystem is already duplicating Task workflow | **NOT CONFIRMED** | `ai_layer.epics` was an intentionally empty boundary | Preserved emptiness and strengthened capability + AST ownership gates against future Task-lifecycle duplication |
| Interfaces contain direct persistence/business state-machine authority | **NOT CONFIRMED as a blocking issue** | CLI/MCP/API already route through application/task contracts; architecture policy forbids Interfaces -> Infrastructure | Kept thin-adapter model; added operation actor/correlation context; no remote API added |
| Verification is sandboxed | **NOT CONFIRMED** | Runner uses local `subprocess.run`, bounded argv/cwd/timeout but inherits local environment | Documented trusted-local/non-sandbox trust model, requires `shell.execute`, extracted replaceable `VerificationExecutor` |
| A separate Execution entity is required now | **NOT CONFIRMED** | Lost/failed attempts are preserved as prior TaskStage rows; recovery creates a new ordinal stage | No duplicate entity added. Revisit only if multiple concrete attempts must exist inside one logical stage identity |
| Production persistence correctness is proven by CI | **PARTIALLY CONFIRMED / INSUFFICIENT** | Existing workflow had no dedicated real-PostgreSQL concurrency/migration job | Added PostgreSQL 16 + pgvector CI gate for fresh/upgrade migrations and cross-session races; local execution remains blocked by environment |
| Strategic infrastructure replacement seams are absent | **PARTIALLY CONFIRMED** | Task/application code is intentionally ORM-centric, verification/snapshot details were concrete | Added used `WorkflowSnapshotStore` and `VerificationExecutor` ports; deliberately did not perform speculative TaskRepository/UnitOfWork big-bang rewrite |

## 3. Architecture Changes

### 3.1 Canonical durable Task recovery state

**Problem.** Task/Stage rows were durable but the repository identity required for completion/recovery lived in mandatory filesystem JSON.

**Decision.** Store immutable repository identity metadata in `repository_snapshots` and reference it from `tasks.baseline_snapshot_id` and `task_stages.start_snapshot_id`. The snapshot contains paths, SHA-256 identities and bounded stat metadata, not source contents.

**Transaction rule.** Snapshot row/reference and Task/Stage transition live in the same DB transaction. Filesystem projection is written only after commit and is best-effort. A DB failure therefore does not publish a required filesystem state; a filesystem failure after commit does not lose canonical state.

**Legacy rule.** Nullable references are retained only so an in-flight pre-0012 Task can promote its old JSON snapshot after digest validation. Missing/inconsistent legacy evidence fails closed.

**Rejected alternatives.** PostgreSQL source-content BLOBs, independent JSON canonical state, speculative object storage.

### 3.2 DB-authoritative concurrency

**Problem.** A filesystem lock cannot prove correctness across independent processes or hosts sharing PostgreSQL.

**Decision.** PostgreSQL is the authority:

- partial unique index: one `active|blocked` Task per Project;
- partial unique index: one `active` TaskStage per Task;
- `FOR UPDATE` around project/task mutation ownership;
- reaper/recovery re-locks the live Task/Stage before acting on a stale candidate;
- `Task.version` increments on authoritative mutations;
- optional `expected_version` rejects stale remote-style writes.

Filesystem locks remain useful for local cache/workspace serialization but may be removed in concurrency tests without changing the expected authoritative result.

### 3.3 Security / Actor / Capability / Approval

Added domain-level actor/capability vocabulary and application-level policy decisions. Capabilities include project/task read/create/start/cancel/approve, workspace/file access, shell execution, Git commit/push and external execution. Durable approvals record requestor, capability/action, status and resolver/decision.

The existing service stays loopback/trusted-local. No unauthenticated remote API was introduced. Future transports must pass operation identity into application policy rather than implement authorization in FastAPI/MCP/CLI/dashboard.

### 3.4 Command idempotency and optimistic concurrency

Added a canonical application command primitive with unique `command_id`, deterministic request hash, actor/correlation attribution and stored result. PostgreSQL advisory transaction locking serializes duplicate keys and a completed receipt returns the original result instead of repeating the mutation.

The command contract requires mutation + receipt to share caller-owned transaction scope. Existing local Task helpers that commit internally are not falsely advertised as remote command handlers. A future remote API must expose transaction-owned application commands through this boundary instead of wrapping arbitrary legacy helpers after the fact.

### 3.5 Workflow extension contract

`StageDefinition` now centrally declares role, read-only/mutating classification, completion contract, required capabilities, allowed outcomes and possible successors for DISCOVERY/IMPLEMENT/REVIEW/FIX. Registry validation prevents incomplete new stages.

Existing semantic transition code is retained because review/finding/remediation behavior is domain-specific; replacing it with a generic workflow framework would add abstraction without reducing risk.

### 3.6 Event backbone

The existing `RuntimeEvent` remains the sole durable journal. It now records correlation/causation, actor, interface, command and schema metadata. Task state and emitted events participate in the same DB transaction. `EventConsumerCheckpoint` establishes a minimal replay/idempotent-consumer cursor contract for future dashboard/WebSocket/mobile/analytics consumers without introducing a broker.

### 3.7 Strategic ports

Two replacement seams are implemented and used:

- `WorkflowSnapshotStore` — persistence-neutral durable snapshot contract with SQLAlchemy adapter;
- `VerificationExecutor` — replaceable execution boundary with current trusted-local subprocess adapter.

A broad TaskRepository/UnitOfWork rewrite was deliberately rejected for this iteration because the current Task Engine is ORM-centric and the rewrite would touch most lifecycle code while providing no additional pre-Epics correctness beyond the targeted transaction/locking changes.

### 3.8 Epic boundary

Epic code remains absent. Architecture policy forbids the reserved capability from direct Task internals, persistence, workspace/snapshot and verification ownership. The architecture gate also rejects Epic-owned primitives named like TaskStage, WorkerLease, VerificationLifecycle, Review/Fix lifecycle, RepositorySnapshot, ReviewFinding or RemediationLoop.

This is an early warning mechanism, not an implementation of Epics.

## 4. Migration Report

### New migration

`0012_architecture_hardening`

Adds:

- `repository_snapshots`;
- Task baseline snapshot FK + monotonic `version`;
- TaskStage start snapshot FK;
- Task/Stage status checks and partial unique indexes;
- RuntimeEvent correlation/actor/interface/command/schema columns;
- `event_consumer_checkpoints`;
- `command_receipts`;
- `approval_requests`.

Before applying uniqueness indexes, migration explicitly checks for duplicate open Tasks / active Stages and fails closed rather than silently selecting a winner.

Snapshot FKs are deferred `NO ACTION`, allowing a Project transaction to cascade-delete Task and snapshot branches without making snapshots independently deletable while referenced.

### Backfill / compatibility

Existing event rows receive explicit legacy attribution defaults during migration; defaults are removed after backfill. Existing Task/Stage snapshot references remain nullable solely for legacy in-flight promotion from validated JSON.

### Executed migration evidence

- static migration graph gate: **PASS**, head `0012_architecture_hardening`;
- real PostgreSQL fresh migration: **NOT RUN** locally;
- real PostgreSQL `0011 -> head`: **NOT RUN** locally;
- CI job and `scripts/postgres_gate.py` implement both scenarios and fail closed when PostgreSQL is unavailable.

## 5. Test / Gate Report

### Actually run successfully

- Full available pytest regression using an external compatibility shim for unavailable MCP/pgvector packages: **397 PASS**.
- PostgreSQL-only tests: **7 SKIP**, exactly because `AI_LAYER_TEST_POSTGRES_URL` is not configured.
- Total collected after hardening: **404**.
- `tests/test_architecture_hardening.py`: **11 PASS**.
- Architecture/complexity/Epic-boundary gate: **PASS**.
- Migration graph gate: **PASS**.
- Skill contract gate: **PASS**.
- Governance gate: **PASS** after documented reviewed re-baseline.
- Release/package gate with deterministic wheel check: **PASS**.
- Independent wheel build A vs B: **same SHA-256**.
- `git diff --check`: **PASS**.
- `python -m compileall` over source/migrations/scripts/tests: **PASS**.

The test-only shim is outside the repository and is not packaged. It provides a minimal `mcp.server.MCPServer` surface and pgvector SQLAlchemy `cosine_distance` comparator solely because the audit container lacks those locked runtime packages.

### PostgreSQL concurrency tests added but not executed locally

The CI gate intentionally removes filesystem-lock authority and races independent SQLAlchemy sessions for:

1. direct duplicate open Task insert;
2. concurrent Task creation;
3. concurrent delegation to different workers;
4. concurrent completion of the same stage;
5. concurrent lost-worker recovery;
6. durable snapshot visibility across sessions;
7. Project deletion across deferred Task/snapshot FK graph.

Expected invariant for mutations is exactly one authoritative success.

### Mandatory checks not run / not PASS

- `scripts/postgres_gate.py`: **NOT RUN successfully** — fails closed with `AI_LAYER_TEST_POSTGRES_URL is required`.
- Ruff format: **NOT RUN** — `ruff` missing.
- Ruff lint: **NOT RUN** — `ruff` missing.
- mypy: **NOT RUN** — `mypy` missing.
- official CPython 3.12 canonical gate: **NOT RUN** — container is CPython 3.13.5.
- real MCP SDK/IDE host and `systemd --user` black-box recovery: **NOT RUN** in this container.

One diagnostic all-in-one quality-gate invocation exceeded the command timeout while repeating the full suite/release workload; this timeout is not counted as PASS or as a discovered code failure. Its constituent executable gates are reported individually above.

## 6. Repeat Architecture Readiness Audit

Question: **If functionality grows another 10x, what breaks first now?**

The first likely pressure points are no longer canonical Task state, Task concurrency, security vocabulary, workflow extension or event transport separation. They are maintainability/capacity seams:

- several pre-existing modules are near the 500-line hard ceiling (`tasks/views.py`, `skills/service.py`, `mcp/tools/tasks.py`, `projections/dashboard.py`, `memory/service.py`, `tasks/lifecycle.py`);
- application/task services remain substantially SQLAlchemy-centric, so a future second persistence backend or much larger command surface may justify incremental TaskRepository/UnitOfWork extraction;
- repository snapshots are metadata identities, not source backups: recovery can compare/fail closed but intentionally does not restore arbitrary lost source content;
- simultaneous repository-writing workers remain unsupported even though control-plane concurrency is DB-safe; worktree/merge/conflict/provenance policy is a separate future design problem;
- a future remote API must use the transactional idempotent command boundary and capability policy rather than call internally committing Task helpers directly.

These are P2/future-scale concerns, not a justification for implementing Epics or distributed infrastructure now.

## 7. Remaining Risks

### P0

- **Validation blocker:** real PostgreSQL migration/concurrency/recovery tests have not executed in this environment. Until they pass, the most important P0 implementation changes are not proven against production persistence semantics.

### P1

- **Validation blocker:** canonical Ruff + mypy checks on supported CPython 3.12 have not executed.
- Real MCP SDK/host + daemon restart acceptance is still required to prove backward compatibility of the installed runtime around this source change.

### P2

- Large cohesive modules remain close to maintainability hard ceilings. Do not raise limits; extract only when the next feature creates a real ownership seam.
- Application/Task code is still ORM-centric outside the two strategic ports. Continue incremental extraction if future capabilities require independent persistence/testing boundaries.
- Production signed update-channel acceptance depends on external publisher infrastructure.

### P3

- Filesystem materialized snapshots may disappear and be regenerated; this is expected behavior, but operators should not treat them as backups.

## 8. Final Verdict

```text
NOT READY FOR EPICS
```

Blocking reasons only:

1. the mandatory real PostgreSQL 16 + pgvector migration/concurrency/recovery gate has not run successfully;
2. the mandatory supported-runtime Ruff format/lint and mypy gates have not run.

No additional source-level architecture rewrite is recommended before those gates are executed. If they pass, perform the final supported-host MCP/service smoke acceptance and then re-evaluate promotion without adding speculative foundation work.
