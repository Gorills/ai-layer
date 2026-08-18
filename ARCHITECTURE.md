# Architecture

## Dependency direction

Interfaces call application use cases. Application coordinates capabilities. Domain contracts are transport- and persistence-independent. Infrastructure/runtime adapters implement PostgreSQL, filesystem and process behavior. Dashboard is a read side over projections, not a second Task/Skill/Epic implementation.

The executable dependency graph lives in `release/architecture-policy.json` and is checked by `scripts/architecture_gate.py`. It validates Python import SCCs, package/capability SCCs, forbidden capability edges and the protected Epic boundary.

The codebase is intentionally migrated incrementally rather than forced into an academic big-bang Clean Architecture rewrite. Strategic replaceable seams are explicit where failure/coupling matters now: durable workflow snapshots use `WorkflowSnapshotStore`; authoritative command execution uses the application idempotency boundary; verification execution uses `VerificationExecutor`. Existing ORM-centric Task services are retained until extracting a broader TaskRepository/UnitOfWork produces concrete value without destabilizing lifecycle semantics.

## Capability map

- **Projects / Project Registry** — durable machine project identity and initialization.
- **Tasks** — Task lifecycle, state machine, delegation contract, bounded remediation and authoritative `task_next` navigation.
- **Epics** — durable specification versions, audit history, explicit human approval, Phase 0/source reconciliation, ordered Task scheduling, drift reconciliation, whole-Epic completion and archive. Epics choose which existing Task is eligible next; they never own per-Task stage/worker/verification/finding semantics.
- **Agents** — typed `AgentRequirement` and host-specific tier/profile mapping; actual-model assurance is recorded separately from requested model.
- **Skills** — canonical skill content, validation, selective retrieval, native Agent Skills materialization and package management. Skill relevance for Cursor/Codex/Antigravity is host-owned, not routed by AI Layer.
- **Context** — reviewed Project Knowledge, durable history/sessions and focused task-specific context assembly; current-source discovery remains host-native. Active Epic context is a compact navigation pointer, not a duplicated full spec.
- **Verification** — replaceable execution boundary and durable verification evidence.
- **Workspace** — repository identity/deltas plus disposable review workspace lifecycle.
- **Observability** — structured durable event journal and runtime measurements.
- **Projections** — read models consumed by Dashboard/API, including Epic list/detail views.
- **Installation / Integrations** — immutable runtime lifecycle, service, host bridges and signed updater.
- **Interfaces** — CLI, MCP and HTTP composition/transport adapters.

## Project Knowledge and source-discovery boundary

AI Layer follows a native-source-first contract:

```text
Host-native tools        -> current source search/read/symbols/references
Deterministic scanner    -> file identity, hashes, manifests/import/test/config evidence, freshness
Project Knowledge        -> reviewed semantic overview/subsystems/invariants/constraints/unknowns/source pointers
Task/Decision/Epic history -> what changed, what was approved/decided, why, and verified outcomes
```

The scanner does not create semantic chunks of current source. Curated Project Knowledge is stored as evidence-backed cards in the existing `Knowledge` store and moves through `DRAFT -> VERIFIED -> STALE/SUPERSEDED`. Evidence fingerprints bind each card to the repository paths used to justify it. A changed/deleted evidence path invalidates the affected card; it does not force a full project-memory rewrite.

Knowledge authoring is deliberately coupled to the existing Task review lifecycle instead of introducing another workflow engine. Only a delegated IMPLEMENT/FIX stage in a review-gated Task may write DRAFT cards. Before a passing REVIEW can publish those drafts, the active review stage must have retrieved them through the Project Knowledge read path; this inspection is recorded in the durable event journal. A VERIFIED overview is the minimum initial baseline readiness signal.

`memory_context` retrieves only reviewed/stale knowledge cards plus relevant Task/Decision history and compact scanner evidence. Source pointers are navigation hints; current repository files remain authoritative. For an active Epic it adds only key/title/status/execution-spec version and the instruction to return to `epic_next`; the full Epic specification remains a durable on-demand read through `epic_get`. Old scanner semantic rows are compatibility debris and are lazily deleted by scanner schema v4 refresh.

## Canonical Task state and transaction boundaries

PostgreSQL is the canonical durable authority for active workflow state. Task and TaskStage rows reference immutable `repository_snapshots` containing repository identity metadata (`path`, content hash and bounded stat metadata), not source contents. The database transaction therefore knows exactly which baseline/stage-start snapshot belongs to a transition.

Filesystem `baseline.json`, `stage-*-start.json`, `current.json` and `latest.json` files are materialized projections/cache. New transitions do not require them for correctness. Snapshot rows/references and Task/Stage state commit together; projection is published only after commit and projection failure does not roll back or invalidate canonical state.

Legacy in-flight rows may have null snapshot references. On first recovery use, a legacy JSON snapshot is accepted only if its digest matches the durable Task/Stage digest, then it is promoted to PostgreSQL. Missing/inconsistent legacy evidence fails closed.

Critical concurrency is also database-authoritative: project/task rows are locked with `FOR UPDATE`, PostgreSQL partial unique indexes enforce at most one open Task per Project and one active Stage per Task, and `Task.version` provides an optimistic concurrency token for future remote-style commands. Filesystem locks are supplemental only.

## Task state machine and extension contract

Workflow, risk, complexity, uncertainty and quality/cost preference are independent dimensions. `task_next` is authoritative; transports do not reconstruct transitions.

`StageDefinition` centrally declares every stage's role, read-only/mutating class, completion contract, required capabilities, allowed outcomes and possible successors. Registered stages are currently `DISCOVERY`, `IMPLEMENT`, `REVIEW` and `FIX`; registry tests require every stage to have a complete definition. Semantic review/remediation rules remain in the Task Engine rather than becoming a generic BPMN engine.

The preserved main paths are:

```text
IMPLEMENT -> REVIEW -> DONE
IMPLEMENT -> REVIEW -> FIX -> REVIEW -> DONE
```

with the existing bounded remediation/human-attention policy.

Workers return results; they do not independently mutate Task Layer state. Delegation binds a worker before managed repository mutation. Existing dirty work uses explicit adoption rather than retrospective attribution. Discovery/review are read-only. Worker loss/lease expiry retains the failed stage as history and creates a new ordinal stage only when repository provenance is clean; changed/missing recovery state blocks fail-closed.

## Epic lifecycle and Task ownership

Epic state is durable PostgreSQL state with four persistence owners: `epics`, immutable `epic_spec_versions`, append-only `epic_audits`, and ordered `epic_plan_items`. Application services are split by responsibility: specification lifecycle, planning/reconciliation, execution/navigation, and shared read helpers. `ai_layer.epics` itself contains only persistence-independent domain contracts and therefore remains protected from Task/DB/Workspace/Verification dependencies.

The high-level lifecycle is:

```text
DRAFT SPEC
  -> unlimited AUDIT / SPEC REVISION
  -> explicit HUMAN APPROVAL
  -> PHASE 0 analysis-only Task
  -> reconciled EXECUTION SPEC
  -> ordered STANDARD Task plan
  -> work Task -> work Task -> ...
  -> mandatory final docs/knowledge/whole-Epic review Task
  -> COMPLETED
  -> ARCHIVED
```

Approval records `approved_spec_version`; Phase 0 never mutates that historical version. If current source requires an obvious correction or one clearly superior durable recommendation, reconciliation creates/uses a newer execution specification with rationale. A genuine material product/architecture trade-off records `human_decision_required` and blocks scheduling instead of guessing.

No implementation plan is authoritative before Phase 0. Phase 0 is an existing `analysis_only` Task, so the existing Task Engine technically enforces read-only behavior. After reconciliation, each work item is created as an ordinary `STANDARD` Task and therefore receives the existing delegation, implement, independent review, fix/remediation, verification and recovery contracts.

`epic_next` is the sole Epic navigation authority. It may tell the orchestrator to start Phase 0, create the post-Phase0 plan, start exactly one eligible ordinary Task, continue that Task through `task_next`, reconcile detected repository drift, start final review, request human attention, or archive. Interfaces and Dashboard do not reconstruct this state machine.

After Phase 0 and every accepted Epic Task, application orchestration records repository identity. If the repository differs before the next planned item starts, normal scheduling blocks and a targeted `analysis_only` drift Task reconciles only affected remaining assumptions. This protects a long-running Epic without taking ownership of Task repository snapshots/workspaces.

The mandatory final Task is still an ordinary `STANDARD` Task. Its IMPLEMENT stage updates current project documentation and DRAFT Project Knowledge. Its independent REVIEW stage must inspect those drafts and review the whole implemented Epic against the execution specification and Definition of Done, not merely the final documentation delta. Existing Task findings and FIX -> REVIEW remediation remain authoritative. Epic completion adds two mechanical closure checks: relevant project documentation changed and the reviewed Task emitted `KnowledgePublished` with at least one published card. If either is missing, another final closure/review item is scheduled instead of archiving an incomplete Epic.

See ADR `DECISIONS/0016-epics-v1-lifecycle.md`.

## Security and command boundary

Domain concepts `Actor`, `Capability` and `PolicyDecision` establish identity/authorization vocabulary. The application layer owns policy decisions and durable `ApprovalRequest` records. Current capability vocabulary covers project/task reads and mutations, workspace/file access, shell execution, Git commit/push and external execution. Transport adapters pass operation context; they do not own authorization policy.

The current service remains trusted-local and loopback-only. This release does not expose an authenticated remote API.

Future mutating remote transports must use the canonical application command boundary with `command_id`/request hash and correlation/actor metadata. A completed command receipt allows a lost-response retry to return the original result instead of repeating the side effect. The command handler and completed receipt must share caller-owned transaction scope. `Task.version`/`expected_version` is available for stale-write rejection where a command depends on a previously observed state.

## Durable events and read side

`RuntimeEvent` remains the single durable event journal; no parallel dashboard/remote event truth is introduced. Events include event type/id/time, aggregate identity, schema version, correlation/causation, actor, interface, optional command id and payload. Task business-state changes and their events are flushed/committed in the same database transaction. Epic lifecycle/scheduling writes append Epic events to the same journal.

`EventConsumerCheckpoint` provides a minimal cursor contract for idempotent/replayable local consumers. Dashboard/WebSocket/mobile/analytics consumers can be added later without changing Task or Epic lifecycle. No message broker is required at this stage.

Dashboard reads projections. Epic Dashboard endpoints expose spec/history/audits/plan as read-only projections. If PostgreSQL reads fail, an explicitly labelled `disk-fallback` Task projection may be shown as degraded/stale information; mutations never fall back to filesystem state.

## Verification security

Worker-reported checks are not AI Layer verification. `VerificationResult` distinguishes `reported`, `host_verified` and `ai_layer_verified`.

The current executor runs argv without a shell, constrains cwd to the registered project, bounds timeout/output/overrides and stores durable evidence. It inherits the trusted local process environment and is **not a sandbox**. Application policy requires `shell.execute`; a `VerificationExecutor` port allows a future container/sandbox/remote executor without changing Task semantics.

## Review findings

Findings are durable structured records with severity/category/path/problem/required correction, provenance, state and verification history. A fixer moves a finding to verification-pending; an independent review/verification flow closes it. Epic Layer reuses Task findings/verification and does not create a parallel per-Task finding system. Epic audits are pre-approval specification-review history, not substitutes for execution findings.

## Target-project footprint

`standard` mode is a zero-footprint attachment: project metadata/rules live under the machine AI Layer home, MCP/bootstrap delivery is global, and project-specific native skills are namespaced into user-level host catalogs. The legacy `external` mode is retained as a compatibility spelling for the same repository-clean attachment behavior. `strict-private` uses the same machine-side layout plus provenance prohibition and a Git privacy guard. Upgrade/repair migrates verified legacy `.ai-layer` state out of older standard repositories and removes only AI Layer-owned project MCP/skill residue while preserving unrelated user configuration.

## Epic boundary rule

Epic code may own specification versions, audit/approval history, Phase 0 and drift reconciliation policy, ordered Task scheduling, acceptance aggregation, whole-Epic integration review and completion/archive state. It orchestrates existing Tasks and cannot duplicate Task worker leases, TaskStage/review/fix/remediation, verification, repository snapshot/workspace or finding lifecycle. The static architecture gate protects this dependency direction mechanically.
