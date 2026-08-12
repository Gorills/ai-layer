# Current State — v0.13.1 semantic Project Map enrichment

## Implemented source state

AI Layer now uses **Project Intelligence + Durable Work State + Observability** as its primary architecture. Native coding-agent hosts remain the normal execution engine.

- **Project status:** `project_status` is the cheap first state call for registered-project work. It restores Git/worktree state, current managed Task, executing/open Epic state, continuation focus and Project Map freshness without running Task/Epic navigators or scanning source.
- **Continuation:** requests such as “continue” use durable `current_focus`. Active managed Task wins; otherwise an executing Epic is resumed; with neither, the request is treated as new native work.
- **Project Map:** scanner schema v5 builds a dedicated metadata-only `project_navigation` index containing paths, language, compact purposes, imports, risk flags and bounded symbols/routes plus vector embeddings. Raw source bodies are not persisted.
- **Semantic Project Map:** `project_navigation_semantics` stores bounded agent-authored navigation learned from real source work: concise responsibilities/purpose, multilingual domain aliases, current important symbols and related files/tests. Scanner-owned structural facts remain immutable to agents.
- **Project Map reconciliation:** `project_map_reconcile` validates current paths/symbols, records Task provenance and checked scope, permits an explicit factual no-change result, and binds semantic freshness to the source content hash. Completed meaningful Tasks are prompted to reconcile only what they learned; the final Epic Task must emit scoped reconciliation evidence before closure.
- **Project search:** `project_search` combines semantic Project Map similarity with lexical path/symbol/purpose/import matches and returns a small ranked set of breadcrumbs and related tests. Current repository source must be opened before code-truth claims or edits.
- **Project Knowledge:** reviewed semantic facts/invariants remain separate from Project Map. `knowledge_search` is the explicit API; `memory_search` remains a compatibility alias. Evidence changes still make affected VERIFIED cards stale.
- **Decisions:** `decision_search` remains the durable architectural-history channel.
- **Legacy context:** `memory_context` remains for compatibility but is informational only. It no longer invokes `task_next`, selects workflow authority or acts as the mandatory project bootstrap.
- **Native execution:** global bootstrap no longer disables source reads, edits, shell, tests, code search or native subagents. If a precise location is known, the host inspects it directly after status; if location is unknown, Project Map is consulted before broad repository discovery.
- **Tasks:** durable Task records, stages, findings, worker leases, provenance/adoption, review sandboxes, verification evidence, remediation caps and MICRO/STANDARD/DISCOVERY_FIRST/ANALYSIS_ONLY profiles remain implemented. `task_next` is authoritative inside an active/selected managed Task, not for every repository action.
- **Epics:** immutable specs, audits, approval, planning, linked Tasks, drift/reconciliation, intervening review, completion/archive and Dashboard views remain implemented. `epic_next` is authoritative inside an active/selected managed Epic.
- **Strict workflow:** independent IMPLEMENT/REVIEW/FIX boundaries and read-only REVIEW/DISCOVERY are preserved as managed-workflow guarantees rather than universal host restrictions.
- **Skills:** Cursor, Codex, Claude Code and Antigravity receive AI Layer skills through their native skill locations. Host-native relevance/progressive disclosure owns normal activation; explicit `skill_get` remains available.
- **Model policy:** ordinary work is host-native. Managed routing retains optional cost-tier metadata; default `economy` can request the configured cheap worker, while `balanced` and `strong` inherit the host by default. Requested model/cost effect remains explicitly unverified when host telemetry is unavailable.
- **MCP runtime:** `project_status` is a fast replay-safe call. `project_search`, `knowledge_search`, legacy context search and decision search use the context/embedding runtime class and warm persistent core.
- **Dashboard:** project pages preserve Tasks/stages/findings/skills/agents and now expose Project Intelligence summary: current focus, Project Map file/symbol counts and freshness.
- **Observability:** Project Intelligence calls emit bounded audit metrics without pretending host-hidden model/token/billing information is measured truth.
- **Privacy:** Project Map stores navigation metadata rather than raw source. External/strict-private project modes continue to keep managed state/material outside target repositories according to their existing contracts.

## Database and migration state

Alembic migration `0016_project_map_semantics` adds the separate semantic navigation table and HNSW cosine index on top of `0015_project_navigation`. It is additive and does not reset Project/Task/Epic/Knowledge/Decision state.

The incremental scanner deletes/rebuilds Project Map rows only for changed/reparsed source paths and reuses unchanged navigation embeddings. Scanner schema v5 triggers construction of the new map from older scanner state.

Real PostgreSQL/pgvector hardening CI has exercised the new migration successfully during development.

## Architectural boundary

The intended execution path is:

> **project_status → project_search when location is unknown → current-source verification → host-native execution → durable recording/strict workflow only where useful**

Project Map answers **where**. Project Knowledge answers **what is already understood**. Decisions answer **why**. Tasks/Epics answer **what work is active**. Source code remains final implementation truth.

AI Layer must not rebuild a second generic agent runtime around native hosts. A new control-plane requirement should justify itself by reducing rediscovery, preserving durable state/evidence or improving measured reliability.

## Release validation status

Release **0.13.1** is promoted in the source branch with an aligned deterministic application wheel, release manifest and governance baseline. ADR 0017 records the execution-model change.

Merge/release readiness still requires the committed clean head to pass:

- canonical formatting/lint/type/architecture/migration/skill/governance/test/release gate;
- real PostgreSQL/pgvector hardening;
- deterministic packaging checks against the declared 0.13.1 release artifacts.

After merge, supported-host field acceptance should exercise `project_status`, Project Map search, continuation, native execution, optional managed Task/Epic flows, dashboard visibility and native skills on real projects.
