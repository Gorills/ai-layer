# Current State — v0.12.0 Epics v1 candidate

## Implemented source state

The foundation now includes the first complete durable Epic capability while preserving the existing Task Engine as the only per-Task execution state machine.

- **Epics:** durable immutable specification versions, unlimited DRAFT audit history, explicit human approval, Phase 0 reconciliation, ordered Task plan, drift reconciliation, final whole-Epic review/closure and archive are implemented.
- **Epic approval:** `approved_spec_version` preserves exactly what the human approved. Phase 0/drift corrections create a newer execution spec instead of silently rewriting the approved baseline.
- **Phase 0:** the first execution Task is always an ordinary `analysis_only` Task. Current repository source is authoritative; non-branching/clearly superior durable corrections are applied automatically, while only genuine material product/architecture trade-offs block for human input.
- **Epic Tasks:** implementation and final items are ordinary sequential `STANDARD` Tasks. Task Engine remains sole owner of worker leases, IMPLEMENT/REVIEW/FIX lifecycle, repository snapshots, verification, findings and remediation.
- **Epic drift:** accepted repository identity is recorded after Phase 0 and each completed Epic Task. External repository drift before the next plan item requires targeted read-only reconciliation.
- **Epic closure:** the last successfully completed Task updates relevant project documentation and drafts Project Knowledge, then independently reviews the whole implemented Epic against the execution spec/Definition of Done. Mechanical completion additionally requires documentation changes and actual reviewed `KnowledgePublished` evidence; otherwise another final review attempt is scheduled.
- **Epic recovery/navigation:** `epic_next` is the authoritative Epic navigator. `memory_context` exposes compact active-Epic state so a new/weak-model chat can recover without loading the full specification on every request.
- **Epic Dashboard:** project pages expose Epics; detail pages render the current human-readable specification, approved/execution versions, audit history, Task plan and spec history through read-only projections.
- **Skills:** Cursor/Codex/Antigravity own skill relevance; AI Layer owns canonical skill content, validation, native descriptor sync and targeted `skill_get` retrieval. The built-in `epics` skill contains the full operating contract for weak models.
- **Current source:** host-native code search/read owns current implementation discovery; AI Layer does not build a parallel semantic source index.
- **Scanner:** `ai-layer scan` owns deterministic repository evidence, hashes/file identity, bounded project signals and freshness/invalidation. Scanner inference is labelled evidence, not reviewed semantic truth.
- **Project Knowledge:** model-authored evidence-backed cards capture durable overview/subsystem knowledge, invariants, constraints, explicit unknowns and source pointers.
- **Knowledge publication:** Mapper/Fixer can write only DRAFT cards in review-gated Tasks. A passing reviewer must first retrieve the task's DRAFT cards; successful review publishes VERIFIED cards. A reviewed overview is required for baseline readiness.
- **Freshness:** supporting-file fingerprint changes move only affected VERIFIED cards to STALE. Cancelled-task drafts become SUPERSEDED.
- **History:** durable completed Tasks, Decisions, WorkSessions and archived Epics remain separate first-class history sources.
- **Context:** ordinary coding tasks get a compact semantic Project Knowledge brief; explicit Project Knowledge audits get a complete compact inventory-first view; explicit continuation prompts get a session-first brief; active Epic state adds only compact navigation metadata. Stale scanner/profile facts are withheld. Automatic raw-source memory and automatic domain skill bodies remain zero.
- **Policy/bootstrap:** static AI Layer rules have one owner in each host’s global native instruction surface. Runtime Task procedure is owned by `task_next`; Epic procedure is owned by `epic_next` plus the native `epics` skill.

## Upgrade behavior

Alembic migration `0014_epics_v1` adds durable Epic, specification-version, audit and plan-item tables. It is additive and does not reset existing Project/Task/Knowledge state. The supported migration gate still starts at the declared minimum `0010_adaptive_task_workflow` and upgrades through head; the PR PostgreSQL hardening job has already exercised the new migration successfully on real PostgreSQL/pgvector during development.

## Release validation status

Canonical CI remains the source of truth for release readiness. Before merge, the final branch must pass both canonical `quality` and real PostgreSQL `postgres-hardening`, include a source-fresh deterministic 0.12.0 installable wheel, and have the governance baseline refreshed for protected policy/version files.

After merge, real supported-host field acceptance remains required before declaring the release fully promoted: clean install/update, daemon/dashboard/MCP runtime, a real Epic create→audit/revise→approve→Phase0→STANDARD Tasks→final review→archive flow, recovery across service/worker interruption, and multi-project reconciliation where applicable.
