# Changelog

## 0.14.0 — Durable Work spine and truthful observability

- Added first-class `WorkItem` and `AgentRun` lifecycle for ordinary host-native user work while keeping managed Tasks/Epics as optional stricter assurance. Multiple WorkItems may coexist per project; the managed Task single-open constraint does not leak into ordinary work.
- Added idempotent `work_begin`, milestone `work_checkpoint`, and terminal Work MCP commands backed by the existing `CommandReceipt`/advisory-lock boundary.
- Added additive schema `0017_work_spine` with durable Work/AgentRun records, Work-provenanced semantic Project Map rows, and `runtime_event_context` correlation for Work/Run/Task/Epic and host/session/model identity.
- Made `RuntimeEvent` the durable human activity journal and kept JSONL/context trace diagnostic-only; stdio bridge/core execution shares one correlation identifier and common MCP execution records safe linked terminal operation evidence without copying raw prompt/source bodies.
- Restricted durable Work evidence to bounded check and repository-delta metadata with explicit assurance; raw commands, output and source content are rejected.
- Made Dashboard project state truthful: live ordinary work requires a non-stale AgentRun; managed Task state and MCP bridge traffic are displayed separately and no longer prove that user work is currently executing.
- Added versioned, bounded Dashboard Work list/detail API contracts with project/status filters, deterministic ordering, batch-loaded AgentRuns, Task/Epic link keys, and a privacy-safe durable event timeline.
- Replaced offset-based technical activity with Activity API v2 and a milestone-first Dashboard timeline using filter-bound keyset cursors, deterministic timestamp/UUID ordering, full Work/Task/Epic/actor/date/type/status/importance/assurance filters, and explicit access to diagnostic all-event detail.
- Added bounded effective project policy to `project_status` with version/hash and corrected the repository bootstrap to the canonical root `DECISIONS/` ADR directory.
- Published Search Contract v2: non-English intent uses a concise English code-centric primary Project Map query, preserves exact identifiers, allows at most one original/mixed widening variant, and requires current-source verification.
- Added unit and real PostgreSQL regression coverage for concurrent Work sequence allocation, idempotency, event correlation, Work-to-Map provenance, cursor-stable safe activity presentation and filtering, project policy, multilingual search fusion and truthful Dashboard state; the canonical PostgreSQL gate discovers every `postgres`-marked contract.

## 0.13.3 — Live agent contract and repository hygiene

- Audited every agent-facing control-plane surface: native/MCP bootstrap, `project_status`, Task/Epic navigation, MCP descriptions, recovery/error guidance, skills and compatibility paths now describe the current Project Intelligence architecture consistently.
- Made the versioned live runtime contract the procedural authority over historical Task/Epic prose; ordinary host-native work no longer inherits the old mandatory Task permission model, while active managed work still follows `task_next`/`epic_next`.
- Rewrote the `epics` native skill around the real ordered AI Layer state machine and current Project Map closure contract instead of generic DAG/orchestration advice.
- Made installed bootstrap readiness version-aware so `doctor`/integration status can detect stale global instructions rather than accepting any historical managed block.
- Promoted `knowledge_search`/`search_knowledge` to canonical internal names while retaining explicit `memory_search` compatibility aliases; legacy `memory_context` remains diagnosable but is not a successful current-flow start.
- Updated QA, smoke and audit flows to start from `project_status`; legacy `memory_context`-first flows now surface a compatibility warning and fail current-contract validation instead of defining success.
- Removed accidental architecture constraints such as exact bootstrap byte size, exact skill/policy-rule counts, transitive dependency-count floors and brittle exact prose assertions; retained real safety/protocol/performance limits and named meaningful compatibility bounds.
- Centralized bootstrap/integration compatibility versions, cleaned stale `Task Layer`/memory wording, added semantic governance regression tests and ADR 0019. No database migration; target remains `0016_project_map_semantics`.

## 0.13.2 — Project Map runtime contract hardening

- Compacted MCP-facing `memory_context` into a compatibility brief instead of returning the legacy multi-surface context payload; focused Project Intelligence APIs remain the preferred path.
- `memory_context` without `task`/`query` now fails soft to `project_status` instead of producing a validation error during legacy/weak-agent startup.
- Added a versioned runtime Project Map capability contract that explicitly names `project_search` for reads and `project_map_reconcile` for updates, including scope, provenance, multilingual aliases and honest no-change semantics.
- Published the current Project Map contract through `project_status`, native/MCP bootstrap and every `epic_next`, so Epics created before Project Map existed learn current behavior dynamically.
- Epic finalization no longer creates another final Task when documentation and Project Knowledge are complete but only `ProjectMapReconciled` evidence is missing; it waits on reconciliation against the already-completed Task.
- Added regression tests for compact legacy context, no-task fallback, old-Epic Project Map guidance and map-only Epic closure behavior. No database migration.

## 0.13.1 — Agent-maintained semantic Project Map

- Added a separate agent-authored semantic Project Map layer over scanner-owned structural navigation; agents cannot overwrite deterministic paths/symbols/imports/hashes or persist source bodies.
- Added `project_map_reconcile` with bounded validation, exact current-symbol/path checks, Task provenance, explicit checked scope and honest no-change reconciliation.
- Semantic navigation is source-hash bound: changed source makes enrichment stale and search down-ranks it until later real work reconciles that area.
- Added concise English canonical purposes/responsibilities/hints plus materially useful multilingual `domain_terms`; `project_search` accepts Russian, English or mixed queries without a forced translation step.
- Integrated bounded Project Map reconciliation guidance into completed Tasks while allowing MICRO/cosmetic work with no reusable navigation knowledge to skip it.
- Made scoped `ProjectMapReconciled` evidence mandatory for the final Epic Task alongside existing documentation and reviewed Project Knowledge closure evidence.
- Split semantic write/reconciliation and search/ranking paths to stay within production module complexity limits, and made structural/semantic retrieval fail soft when embeddings/vector search are unavailable.
- Added semantic current/stale/missing coverage to Project Intelligence/Dashboard projections and migration `0016_project_map_semantics`.

## 0.13.0 — Project Intelligence control plane

- Replaced the mandatory agent-runtime harness with a Project Intelligence control plane; the host owns ordinary reads, edits, search, shell, tests and native subagents.
- Added cheap `project_status` continuation state plus metadata-only `project_search` breadcrumbs for paths, symbols, imports, purposes, risk flags and related tests; current source remains authoritative.
- Separated Project Map navigation from reviewed Project Knowledge and Decisions; legacy `memory_context` is compatibility-only and no longer drives Task/Epic navigation.
- Preserved Tasks, Epics, findings, verification, review sandboxes, worker provenance/recovery and strict IMPLEMENT → REVIEW → FIX → REVIEW as explicit managed/high-assurance workflows instead of a universal permission layer.
- Published host-native skills to Claude Code as well as Cursor/Codex/Antigravity and retained host-owned progressive skill relevance selection.
- Added migration `0015_project_navigation`, scanner schema v5, incremental Project Map refresh, lexical fallback when embeddings are unavailable, and safe symbol metadata that never persists Python default expressions.
- Extended Dashboard Project Intelligence projections and made read-side degradation tolerant of temporary durable-database unavailability.
- Model/cost telemetry now distinguishes requested/unverified routing from measured economics instead of implying unobserved token or billing truth.

## 0.12.2 — Dashboard background-load fix

- Removed the Dashboard projection dependency on authoritative `task_next` navigation, so passive refreshes no longer trigger repository drift/provenance scans or repository hashing.
- Reused Task state already captured by observability snapshots and made overview Task history lightweight, eliminating duplicate per-project Task reads.
- Replaced the project Epic list N+1/full-history expansion with a lightweight summary query containing only list-view fields.
- Cached native skill catalog counts between project-detail polls instead of rereading every descriptor on each refresh.
- Replaced unconditional 2-second polling with visibility-aware adaptive polling: 3 seconds while work is active, 12 seconds while idle, and no polling for hidden tabs.
- Avoided full Dashboard DOM reconstruction when only volatile generated-at/uptime/idle counters changed.
- No Task/Epic transition semantics, provenance guard, schema, privacy mode or verification behavior changed.

## 0.12.0 — Epics v1

- Activated the protected `ai_layer.epics` capability as a durable specification/scheduling layer over the existing Task Engine, without duplicating Task stages, worker leases, repository snapshots, verification, findings or REVIEW/FIX semantics.
- Added immutable human-readable Epic specification versions, unlimited pre-approval independent audit records, explicit human approval and preserved `approved_spec_version` history.
- Added mandatory source-authoritative Phase 0 as an ordinary read-only `analysis_only` Task before any implementation plan is finalized; obvious/non-branching and clearly superior durable corrections update the execution specification automatically, while genuine material product/architecture trade-offs block for human input.
- Added post-Phase0 ordered Epic plans whose implementation/final items always execute sequentially as ordinary `STANDARD` Tasks through the existing full IMPLEMENT → REVIEW → FIX → REVIEW lifecycle.
- Added repository-drift detection between accepted Epic Task boundaries and targeted read-only reconciliation before future planned work can continue.
- Added the mandatory final closure Task: update project documentation and DRAFT Project Knowledge, independently review the whole implemented Epic against the execution specification/Definition of Done, reuse the existing finding/remediation loop, and mechanically require both documentation changes and reviewed `KnowledgePublished` evidence before completion/archive.
- Added `epic_next` as the authoritative durable Epic navigator plus compact active-Epic recovery state in `memory_context`; weak/new chats no longer need to reconstruct Epic position from conversation history.
- Added the built-in native `epics` skill and bootstrap rules covering create/audit/revise/approve/Phase0/plan/continuous execution/drift/final-review/archive behavior, including the rule that MVP may reduce scope but may not justify knowingly temporary or incomplete selected-scope architecture.
- Added read-only Dashboard Epic list/detail projections and UI for readable specification Markdown, approved/execution versions, audit history, Task plan and immutable spec history.
- Added migration `0014_epics_v1` for durable Epic/spec/audit/plan state and extended structured runtime events for Epic lifecycle/scheduling evidence.
- Added lifecycle, drift, final mechanical closure and Dashboard regression tests plus ADR 0016; real PostgreSQL/pgvector CI exercises the supported `0010_adaptive_task_workflow -> 0014_epics_v1` upgrade path.
- Bumped the installable release to 0.12.0; the committed wheel remains subject to the existing source-fresh deterministic wheel gate.

## 0.11.4 — single-owner policy/bootstrap context economy

- Made the global native host bootstrap the single static AI Layer instruction owner for Cursor, Codex, Claude Code and Antigravity; detailed runtime procedure remains owned by `task_next`.
- Removed AI Layer workflow text from standard-project `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/ai-layer.mdc` and `.agents/rules/ai-layer.md`; upgrades remove only AI Layer-managed legacy blocks and preserve user-authored content.
- Added sparse workspace Antigravity MCP binding at the documented `.agents/mcp_config.json` path alongside Cursor/Claude/Codex project bindings, preserving exact project-root identity without project rule duplication.
- Replaced the multi-kilobyte MCP instruction manual with a tiny fallback contract.
- `memory_context.policy` is now dynamic-only: bundled defaults are omitted, while user-modified global policy, real project rules and strict-private constraints remain authoritative.
- Removed static Task workflow manuals from `memory_context.tool_guidance` and compacted ordinary Task runtime state; full Task state remains available from Task Layer tools.
- Distilled the useful general engineering floor (minimal coherent change, real verification, no speculative dependencies, high-impact/destructive-change caution) into the one global bootstrap rather than dropping it with the duplicated policy.
- Updated smoke/regression tests to enforce zero raw-source memory, zero default dynamic-policy cost and absence of repository-level AI Layer text bridges. No database migration.

## 0.11.3 — continuation context compiler hardening

- Added an explicit continuation presentation for prompts such as `продолжай`, `continue previous task` and `resume work`; session handoff restoration is the primary context source instead of semantic Project Knowledge search.
- Generic continuation text is never sent to `memory_search`; consequential decision lookup can still be requested separately when the user actually asks for a new design choice.
- Continuation context now exposes only a compact recent completed-task summary and compact authoritative Task navigation state; full previous task acceptance criteria, discovery reasoning, findings and internal counters are excluded.
- Scanner evidence and scanner-derived project profile are withheld whenever the deterministic snapshot is stale/refreshing/missing, rather than presenting outdated architecture candidates beside newer Task history.
- Continuation mode also suppresses scanner/profile payload even when fresh because handoff history plus current host-native source inspection are the authoritative continuation surfaces.
- Kept ordinary coding semantic Project Knowledge retrieval and inventory-first knowledge-audit presentation unchanged. No database migration, new router, or new service was added.

## 0.11.2 — task-aware Project Knowledge presentation

- Added an inventory-first `memory_context` presentation for Project Knowledge coverage/correctness audits instead of semantic top-N retrieval.
- Coverage audits now receive a compact complete VERIFIED knowledge catalog plus category counts and stale inventory, with selective expansion only when needed.
- Independent knowledge audits no longer receive previous reviewer `discovery_result`, findings, proposed plans or completion reasoning through `task_runtime`; only minimal prior knowledge-task metadata remains.
- Added a compact read-only audit policy/navigation contract while keeping current repository source authoritative and Task Layer navigation intact.
- Removed duplicate `memory` and `project_intelligence` aliases from `memory_context`; scanner evidence now has one canonical response surface.
- Audit scanner hints no longer expose unreviewed framework/entrypoint candidates when a reviewed knowledge baseline exists.
- Ordinary coding tasks keep semantic relevant-card/history/decision retrieval unchanged. No database migration or new routing/classifier subsystem was added.

## 0.11.1 — dirty-worktree task baselines

- `task_create` now accepts staged, unstaged and untracked pre-existing work and captures the exact repository state as the immutable task baseline.
- Added durable `Task.preexisting_changes` provenance (migration `0013_dirty_task_baselines`).
- `final_changes` and stage deltas remain measured against AI Layer snapshots, so unrelated pre-existing dirty paths are excluded from the managed task delta.
- `task_adopt` is reserved for existing changes that are themselves the implementation being brought under review.
- Agents are explicitly forbidden from using stash/reset/restore/commit merely to satisfy Task Layer cleanliness.
- MICRO tasks that touch a path already dirty at baseline escalate to STANDARD review because a HEAD-based line count cannot honestly represent the task-only line delta.
- Task state schema is now 5.

## 0.11.0 — verified Project Knowledge memory redesign

- Reframed `scan` as deterministic repository evidence/freshness collection; new scans no longer chunk/embed current source or create a second semantic code-search index.
- Added review-gated, evidence-backed Project Knowledge cards with `DRAFT`, `VERIFIED`, `STALE` and `SUPERSEDED` lifecycle, explicit unknowns, source fingerprints and selective invalidation.
- Added explicit knowledge onboarding through the existing standard Task workflow: Mapper writes DRAFT cards, reviewer must actually retrieve/inspect them, FIX/REVIEW uses the existing remediation loop, and only a passing independent review publishes VERIFIED knowledge.
- Require a VERIFIED `overview` card before reporting a complete initial knowledge baseline; a lone subsystem card no longer creates false readiness.
- Redesigned `memory_context` into a compact task project brief containing relevant reviewed knowledge, Task history, decisions, source pointers and bounded scanner evidence; raw current-source memory cost is zero.
- `memory_search` now searches curated Project Knowledge rather than current repository source; host-native source search/read remains authoritative for implementation details.
- Scanner schema v4 lazily removes pre-v0.11 scanner `file`/`architecture`/`project-intelligence` semantic rows on refresh while preserving curated knowledge, decisions and history; no DB migration/reset is required.
- Added knowledge observability (`KnowledgeDraftUpdated`, `KnowledgeReviewInspected`, `KnowledgePublished`), stale/raw-source regression findings and CLI knowledge status/list commands.
- Kept current repository `epic/*` documents as legacy evidence only; no AI Layer Epic implementation was added.

## 0.10.3 — native-first skill routing redesign

- Removed the active AI Layer `required/recommended/on_demand` planner and eager domain-skill core injection from `memory_context`; Cursor, Codex and Antigravity now own skill relevance through their native Agent Skills mechanisms.
- Kept AI Layer as the authoritative skill store with targeted `skill_get` section retrieval, package management, validation, versioning and monitoring.
- Added one thin Agent Skills descriptor renderer and automatic synchronization: Cursor + Codex share `~/.agents/skills`, Antigravity uses `~/.gemini/config/skills`, and standard project skills use `.agents/skills`. External/strict-private project skills use namespaced user-level descriptors to preserve zero footprint.
- Added description quality/catalog gates, removed legacy routing metadata from all 42 built-in skills, and changed the production skill gate to validate native descriptors/selective retrieval instead of classifier outcomes.
- Native publication is upgrade-safe: new/updated skills fail routing-description validation before mutation, while a pre-existing invalid legacy custom skill is retained canonically but blocked individually instead of preventing the rest of the host catalog from synchronizing. Zero-footprint project descriptors carry exact project scope in host-visible metadata.
- Removed router-dependent scanner/dashboard/worker behavior and obsolete required/recommended autoload metrics. Historical `ProjectSkill` rows and `SkillPlanCreated` events remain readable but inactive.
- Reduced the generated project always-on bridge from 10062 to 1549 bytes in the measured reference path; automatic domain-skill content in `memory_context` is now zero bytes.
- Updated context monitoring to distinguish `AI_LAYER_OBSERVED`, `AI_LAYER_CONFIGURED` and `HOST_HIDDEN`, including native catalog configuration and observed targeted/full/repeated `skill_get` fetches.
- No database migration and no Task/Epic state-machine redesign.

## 0.10.2 — context and skill economy observability

- Added automatic per-project context telemetry at the common MCP execution boundary; no agent-side manual logging is required.
- Captures secret-redacted exact payloads for context/navigation tools, size/hash profiles for every MCP result, `memory_context` component breakdown, skill plan/autoload/`skill_get` chain and repeated/full/unplanned skill-fetch findings.
- Captures actual configured Cursor global/project rule files, MCP server instructions, registered MCP tool-contract catalog and installed AI Layer worker profiles while explicitly marking host delivery as not runtime-verifiable.
- Stores diagnostics outside target repositories under machine state, bounds/rotates the raw JSONL trace, and automatically refreshes one portable `context-report-latest.json` at context/skill/stage/session boundaries.
- Added `ai-layer context-report --path ... --output ...` for a fresh portable forensic artifact suitable for later independent analysis.
- Token counts are explicitly approximate and the report does not claim visibility into Cursor/OpenAI system prompts, full chat history, host-side tool-schema inclusion/cache behavior or whether a model cognitively used a skill. No database migration or Task workflow change.

## 0.10.1 — orchestrator discipline hardening

- Added one canonical Critical Orchestrator Contract and load it prominently in global/project bootstrap plus MCP instructions.
- Explicitly forbids top-level repository/external mutations, fallback implementation/fix/review/discovery, and retroactive attribution of orchestrator edits to workers.
- `task_next` now repeats the orchestrator role contract at delegation/completion boundaries and requires actual delegated-worker evidence before completion is recorded.
- `task_stage_delegate` now returns an explicit `START_THE_DELEGATED_WORKER_NOW` handoff instead of leaving the host action implicit.
- Strengthened Cursor writable/read-only worker profiles and delegation contracts with unambiguous role ownership and blocker behavior.
- Added regression tests for bootstrap salience, runtime handoff/preconditions, and worker role contracts. No database migration or Task state-machine change.

## 0.10.0 — pre-Epics architecture hardening

- Made PostgreSQL the canonical durable owner of Task/Stage repository identity snapshots; local snapshot JSON is now disposable best-effort materialization with legacy promotion/fail-closed recovery.
- Added DB-authoritative project/task locking, partial unique invariants for one open Task per Project and one active Stage per Task, Task versioning and optional `expected_version` stale-write protection.
- Added `Actor`, `Capability`, policy decision and durable approval foundations without exposing a remote API; the current service remains trusted-local/loopback-only.
- Extended the single `RuntimeEvent` journal with actor/interface/correlation/causation/command/schema metadata and durable consumer checkpoints.
- Added transactional idempotent-command receipts for future remote/application command boundaries.
- Added a declarative `StageDefinition` registry and architecture tests protecting the Epic boundary from duplicating per-Task lifecycle primitives.
- Added strategic `WorkflowSnapshotStore` and `VerificationExecutor` ports; verification remains explicitly trusted-local and non-sandboxed.
- Added migration `0012_architecture_hardening`, PostgreSQL migration/concurrency CI gate and fault-injection/recovery/idempotency tests.
- Rebuilt the deterministic 0.10.0 application wheel and updated release/governance documentation.

## 0.9.2 — strict-private large tracked-file repair hotfix

- Fixed machine upgrade false-negative when an existing strict-private project contains a clean tracked text file larger than the changed-file privacy scan cap (for example `package-lock.json`).
- Repository baseline privacy audit now streams large tracked text with bounded memory and chunk overlap, so size alone is not treated as a privacy violation.
- Kept changed/staged privacy enforcement fail-closed for oversized text; large tracked content containing AI provenance is still detected by baseline repair.

## 0.9.1 — clean-install bootstrap hotfix

- Split installer validation into a dependency-free stdlib preflight and the full release gate inside the newly installed exact-pinned runtime.
- Prevent clean installs from importing AI Layer runtime modules before dependencies are installed.
- Fail closed with useful preflight/full-gate diagnostics and clean incomplete pre-activation release environments.
- Expanded governance protection to the installer and bootstrap/release-lock/wheel trust-chain scripts.

## 0.9.0 — PRE-EPICS FOUNDATION candidate

- Added executable package/capability architecture graph and stricter complexity ceilings; removed active architecture ratchets.
- Split former CLI/MCP/Task/Skill/Integration/Observability/Dashboard concentration points into focused owners and compatibility composition/facade modules.
- Added application use-case boundary so CLI/MCP/Dashboard do not own database/domain transition logic.
- Added typed domain contracts for task navigation, agent requirements/model assurance, verification, findings, repository deltas, skills and a shared semantic error envelope across core/public transports.
- Added Repository Workspace boundary and real Verification Runner with durable evidence.
- Added structured durable runtime events and Dashboard projections/read models.
- Replaced central slug-specific Skill planner logic with manifest-driven routing and added production skill contract gate.
- Persisted independent task complexity/uncertainty dimensions and actual-model assurance/telemetry.
- Added durable worker leases/heartbeats plus daemon stale-worker reconciliation and explicit fail-closed disconnect recovery without retrospective provenance assignment.
- Added schema revision `0011_pre_epics_foundation`.
- Added governance-sensitive policy baseline and canonical quality/release gates.
- Added signed/checksummed one-command updater client, separated development-repository contents from runtime release contents, and split zero-footprint `external` attachment from `strict-private` provenance/privacy policy.
- Replaced historical/versioned documentation with small source-first canonical documents and ADRs.
- Added only an empty Epic extension boundary; no Epic behavior or persistence.
