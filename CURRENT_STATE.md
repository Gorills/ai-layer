# Current State — v0.14.0 Durable Work spine and truthful observability

## Implemented source state

AI Layer is a Project Intelligence control plane around host-native coding agents. The host remains the execution engine; AI Layer preserves durable project/work state, semantic navigation, reviewed knowledge, optional strict managed workflows, verification evidence and observability.

The current model deliberately separates three identities:

- **WorkItem** — one substantive user-visible unit of ordinary host-native work. Multiple WorkItems may exist in one project.
- **Managed Task / Epic** — optional stricter assurance workflows with their own state machines. The existing single-open-Task rule remains scoped to the managed Task engine and does not constrain WorkItems.
- **RuntimeEvent / AgentRun** — durable evidence of observed activity and lifecycle; activity is never treated as the identity of the user's work.

A WorkItem can record goal, kind, lifecycle status, reviewed/changed paths, repository delta, checks, Project Map disposition, observability coverage, assurance source and optional links to a managed Task/Epic. AgentRun records observed root/subagent identity, host/client/session/turn/model, heartbeat and terminal state. Dashboard may claim ordinary work is live only when a non-stale AgentRun supports that claim; MCP bridge traffic or an open managed Task alone is insufficient.

## Project Intelligence startup contract

`project_status` remains the mandatory first AI Layer state call for registered-project work. It returns a cheap state snapshot:

- current focus and continuation (live Work, active managed Task, or executing Epic);
- bounded effective `project_policy` with contract version, SHA-256, character count and truncation flag, with project/privacy rules preserved if the 12k bound truncates a long custom global prefix;
- git/worktree summary;
- compact live/attention/recent Work rows without AgentRun arrays;
- compact active Task/Epic;
- Project Map freshness (status, stale/missing counts, changed paths).

It does not re-send the runtime procedure, Project Map capability essay, idle `latest_task`, or open Epic lists. Native bootstrap owns ordinary procedure; MCP initialize instructions are the compact fallback when that bootstrap is missing. Short ordinary work should normally use `work_begin` plus exactly one terminal Work call. `work_checkpoint` is reserved for meaningful milestones or blockers, not every file/tool action. Existing managed Task/Epic flows remain available when strict assurance is explicitly useful.

## Project Map and search

Project Map answers **where**. Project Knowledge answers **what is already understood and reviewed**. Current repository source remains final code truth.

For unknown code locations, `project_search` uses a bounded search contract. For non-English natural-language intent the primary query should be concise English and code-centric while exact repository identifiers remain verbatim. At most one original-language or mixed variant may widen domain aliases. End-to-end flow claims should cover the relevant entrypoint/handler, core service/domain, persistence or external integration, and tests. Project Map hits are breadcrumbs and must be verified against current source.

Semantic Project Map enrichment remains canonical-English for purpose/responsibilities/navigation hints, preserves exact code identifiers, and may store useful multilingual aliases in `domain_terms`.

`project_map_reconcile(source_work_key=...)` binds inspected semantic scope directly to ordinary Work provenance, persists `Work.map_disposition` as `reconciled` with that event identifier and checked scope, and returns the ready disposition. A later terminal Work call may omit `map_disposition` to keep that persisted value; an explicit `reconciled` report still requires non-empty checked scope plus the event identifier, and may use `scope_paths` as an alias for `scope`. Honest no-change/not-applicable/deferred dispositions remain available.

## Durable observability

`RuntimeEvent` is the durable event journal. `runtime_event_context` adds Work/Run/Task/Epic and host/session/model correlation without rewriting historical events. The stdio bridge propagates its correlation identifier into core execution, and common MCP execution records safe terminal `OperationCompleted` / `OperationFailed` evidence best-effort. Raw prompts and source bodies are not copied into the human activity presenter.

Existing JSONL/context-trace telemetry remains diagnostic only. Dashboard activity now reads the durable RuntimeEvent journal; Work, managed Tasks, Project Map quality and MCP bridges are presented as separate concepts.

Dashboard exposes versioned, bounded Work list/detail read contracts at `/api/v1/dashboard/work` and `/api/v1/dashboard/work/{project_key}/{work_key}`. The portfolio list supports project/status filters and deterministic ordering, batch-loads AgentRuns, and the detail response includes a safe bounded timeline from the durable RuntimeEvent journal. The Dashboard browser has Work list (`#/work`) and Work detail (`#/work/{project_key}/{work_key}`) pages, and the overview portfolio shows Now (live/non-stale), Needs attention (blocked, stale-active, map pending/deferred), and Recently completed slices from that enrichment.

`/api/v1/dashboard/activity` now exposes Activity contract v2: milestone-first by default (including Epic lifecycle types), bounded by an opaque filter-bound keyset cursor ordered on `(occurred_at, event_id)`, and filterable by project, date range, Work/Task/Epic identity, actor, event type, status, importance and assurance. Task/Epic identity filters read `RuntimeEventContext`; new Task/Epic lifecycle events populate that sidecar, while historical `RuntimeEvent` rows without it stay unfilterable by `task_id`/`epic_id` and are not rewritten. The Dashboard keeps transport-level events available through an explicit all-events mode instead of mixing them into the default human work history.

Current observability is truthful but intentionally incomplete: Work lifecycle visibility is available now, while richer native-host hooks and deeper subagent/tool observation remain future adapter work and are not claimed as implemented in this release.

## Repository governance

The root `AGENTS.md` points to the canonical ADR directory `DECISIONS/`. ADR 0020 records the Work/observability architecture. Agent-facing semantics remain governed by the versioned live runtime contract rather than stale historical workflow prose.

## Release validation status

Release candidate **0.14.0** targets Alembic schema `0018_command_project_scope` and must not be promoted until the exact committed wheel, release manifest and governance baseline are aligned and the canonical quality + PostgreSQL/pgvector gates are green on the final clean head.

After merge, supported-host field acceptance should exercise `project_status`, Work lifecycle/continuation, multilingual Project Map search, optional managed Task/Epic flows, durable activity/Dashboard visibility and native skills on real projects.
