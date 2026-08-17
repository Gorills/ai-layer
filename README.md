# Local AI Development Layer

Local AI Development Layer is a local control plane for AI-assisted software engineering.

Its job is not to replace Cursor, Codex, Claude Code, Antigravity or another coding-agent runtime. The host remains responsible for normal source inspection, edits, shell commands, tests, code search, model choice and native subagents.

AI Layer adds what should survive individual chats and model contexts:

- **Project Intelligence** — a lightweight, reusable map of where relevant code lives;
- **durable work state** — ordinary WorkItems/AgentRuns plus optional managed Tasks/Epics that can be resumed later;
- **Project Knowledge and Decisions** — reviewed facts, invariants and architectural history;
- **native Agent Skills** — authoritative engineering skills published into host-native skill systems;
- **verification and review evidence** — optional strict workflows where extra guarantees are worth the cost;
- **observability and dashboard projections** — a human-readable view of project/workflow/runtime state.

Current package version: **0.14.0**. The source architecture described here reflects the current control-plane implementation; release promotion remains governed by the repository release gate and committed wheel/manifest.

## Core operating model

For registered-project work, the small always-on bootstrap follows this shape:

1. call `project_status(project_root=<workspace root>)` and apply its bounded `project_policy`;
2. use `work.current_focus` / `work.continuation` to resume existing ordinary Work or managed Task/Epic state before creating anything new;
3. with no durable focus, if the user explicitly asks for a managed Task or the standard Task protocol, call `task_create` directly; AI Layer creates or links the backing Work automatically;
4. otherwise, for a new substantive ordinary request call `work_begin`; short work normally needs only one terminal Work call after execution;
5. if a precise file or symbol is already known, inspect current source directly with host-native tools;
6. if code location is unknown, use `project_search` with a concise English code-centric primary query for non-English intent, preserving exact repository identifiers and optionally one original/mixed widening variant;
7. use `knowledge_search` and `decision_search` only when durable facts or prior decisions materially help the task;
8. execute normally through the host runtime;
9. inside an existing managed Task/Epic, follow `task_next` / `epic_next`; a new explicit managed Task starts with `task_create`, not a preliminary `work_begin`;
10. reconcile Project Map only for navigation facts actually established from inspected/affected scope.

The goal is to make already-known project structure cheaper to reuse than to rediscover.

## Project Intelligence

AI Layer deliberately separates four kinds of context.

### `project_status` — what is happening now?

This is the cheap continuation read. It restores:

- registered project identity;
- Git branch/HEAD and dirty-worktree summary;
- active managed Task, if any;
- executing/open Epic state;
- a single current focus for continuation;
- Project Map/index freshness.

It does **not** run the Task navigator, scan source code or hash the entire repository merely to answer “what are we doing?”.

### `project_search` — where should I look?

Project Map is a metadata-only code navigation index. The scanner keeps compact breadcrumbs such as:

- file path and language;
- short deterministic purpose;
- imports/dependencies;
- classes, functions, methods and selected route metadata;
- risk flags;
- relationships to likely tests;
- a semantic embedding of that compact navigation document.

Project Map never persists source bodies. Search combines semantic metadata similarity with lexical path/symbol/purpose/import matches and returns a small ranked set of places to inspect.

Since 0.13.1 the map has two ownership layers. The scanner owns deterministic structural facts. Working agents may add bounded semantic breadcrumbs—concise purpose/responsibilities, useful domain terms, current important symbols and related files/tests—through `project_map_reconcile` after real source work. Canonical semantic prose is concise English, source identifiers remain exact, and `domain_terms` may preserve materially useful Russian or other user/project vocabulary.

Ordinary Work can pass `source_work_key` during reconciliation. AI Layer then stores `source_work_id` provenance and returns the durable reconciliation event identifier used by the WorkItem's terminal Map disposition; managed Task provenance remains available independently.

Semantic enrichment is tied to the source hash it was learned from. When source changes, the old semantic row becomes stale and is down-ranked until real work reconciles it; AI Layer does not launch a duplicate background LLM mapper.

The returned locations are hints. The host must open current repository source before making code-truth claims or edits.

### `knowledge_search` — what do we already know?

Project Knowledge contains model-authored, review-gated semantic facts such as:

- subsystem behavior;
- invariants and constraints;
- integration contracts;
- fragile areas;
- runtime/deployment/testing facts.

Knowledge is separate from Project Map. Project Map answers **where**; Knowledge answers **what is important to understand**. Evidence changes can make reviewed Knowledge stale.

`memory_search` is retained as a compatibility alias for `knowledge_search`.

### `decision_search` — why was this chosen?

Decisions preserve consequential architectural choices and rationale so later agents do not repeatedly reopen already-decided trade-offs without evidence.

## Source of truth

Current repository source is authoritative for code behavior.

AI Layer intentionally does not turn PostgreSQL/vector storage into a second copy of the repository. Project Map contains navigation metadata; Knowledge contains reviewed semantic facts; Decisions contain rationale; Tasks/Epics contain work state.

When an index is stale, it may still provide useful breadcrumbs, but current source must be verified.

## Tasks

Tasks remain a first-class durable capability. They are useful when work benefits from persistent lifecycle/state, independent review, findings, verification evidence, recovery or dashboard tracking.

They are no longer a universal permission gate for every code change.

Managed profiles remain available:

- **MICRO** — bounded localized work with the existing inline managed exception;
- **STANDARD** — IMPLEMENT → REVIEW, with FIX → REVIEW when needed;
- **DISCOVERY_FIRST** — read-only discovery before implementation planning;
- **ANALYSIS_ONLY** — read-only work that can complete without mutation.

A new explicit managed Task starts with `task_create` directly. The application layer creates, reuses or links its backing Work automatically and can repair a missing Task↔Work link on subsequent managed Task operations; the agent does not perform that bookkeeping. Inside an active managed Task, `task_next` remains the authoritative navigator. Existing provenance, worker leases, read-only review/discovery, adoption, review sandboxes, findings, remediation caps and verification mechanisms are preserved.

A dirty worktree is valid user state. AI Layer must not discard/stash/reset user-owned work merely to make a workflow clean.

## Epics

Epics remain the durable outer layer for large outcomes:

- specification and revisions;
- independent audit;
- human approval gate;
- execution plan;
- linked Tasks;
- intervening review;
- drift/reconciliation;
- completion/archive state.

An Epic does not replace native implementation. When an Epic creates/uses managed Tasks, Tasks own their internal stage lifecycle while the Epic owns the larger outcome and integration state.

When `project_status` reports an executing Epic as the current focus and the user asks to continue, `epic_next` resumes the durable workflow instead of reconstructing it from chat history.

## Agent Skills

AI Layer keeps an authoritative skill catalog but relevance selection belongs to the host-native Agent Skills system.

Global/project skills are synchronized to supported native locations for:

- Cursor;
- OpenAI Codex;
- Claude Code;
- Google Antigravity.

The host discovers and loads relevant skill bodies progressively. AI Layer does not centrally inject a domain skill bundle into every task. `skill_get` remains available for explicit authoritative retrieval or section access.

External/strict-private project modes keep project-specific AI Layer state and managed skill material outside repositories according to the privacy contract.

## Model routing and economics

Normal work uses the host's native model/runtime decisions.

Managed Task stages retain model-policy metadata as an optional strict-flow capability. Defaults no longer pretend that two identical configured models form different cost tiers:

- `economy` can request the configured cheap worker;
- `balanced` defaults to `inherit`;
- `strong` defaults to `inherit`.

Requested model/tier is not treated as billing truth. Where the host does not expose actual model/token/cost data, telemetry remains explicitly unverified/estimated.

The optimization target is **total cost to a verified accepted result**, not minimum tokens in one call and not maximum workflow ceremony.

## Dashboard

The local dashboard remains a major product surface. It exposes, without terminal dumps:

- project overview and health;
- bounded durable Work list/detail read models at `/api/v1/dashboard/work` and `/api/v1/dashboard/work/{project_key}/{work_key}`;
- a milestone-first durable RuntimeEvent timeline at `/api/v1/dashboard/activity`, with opaque keyset cursors and bounded project/date/Work/Task/Epic/actor/event/status/importance/assurance filters;
- current Task/stage and review findings;
- Epics;
- Project Intelligence summary (Project Map size/symbols/freshness/current focus);
- Knowledge;
- rules and native skills;
- agent/runtime activity;
- verification and protocol telemetry.

Large collections are cursor-paginated or otherwise bounded rather than rendered as unbounded technical lists. Transport-level events remain available through the timeline's explicit all-events mode; they are not the default human work history.

## MCP/runtime behavior

The persistent local core remains the MCP application boundary.

Workload classes are explicit:

- `project_status` is a fast, replay-safe read;
- `project_search`, `knowledge_search`, `memory_context`, `memory_search` and `decision_search` use the context/embedding runtime class;
- verification/import/update operations retain long-running budgets where required.

A temporary failure of Project Intelligence should be disclosed and should not globally disable safe native source inspection. A failure inside an explicitly active managed Task/Epic transition must still preserve that durable workflow's integrity.

## Scanner and privacy

The incremental scanner stores deterministic file evidence and Project Map metadata. It does not persist raw repository source bodies as semantic memory.

Changed files invalidate/rebuild only their navigation rows; unchanged Project Map embeddings can be reused. Scanner schema v5 introduces the dedicated Project Map lifecycle.

Project Knowledge evidence is hash-bound to scanned paths and can become `STALE` when supporting repository evidence changes.

## Installation and updates

The supported flow remains the repository's one-command installer/updater and immutable machine runtime layout. Runtime state lives under the AI Layer machine home rather than being copied into target projects.

Use the CLI health/update/install commands and generated host integrations rather than manually editing runtime internals. Strict-private/external projects should continue to use the zero-footprint path supported by the installer.

## Quality and release gates

Source changes are governed by the canonical repository gates:

```bash
make quality
make postgres-gate
```

The quality gate covers formatting, linting, typing, architecture/complexity, migrations, skill contracts, governance, tests and deterministic release packaging. The PostgreSQL gate validates the real PostgreSQL/pgvector path and migrations.

Release promotion is fail-closed: package version, committed application wheel, runtime/tool locks and release manifest must agree. A source refactor is not described as a new binary release until that promotion is actually performed.

## Architectural rule of thumb

Use AI Layer when it prevents repeated work or preserves evidence that would otherwise be lost.

Do not make an agent ask AI Layer for permission to do what its native runtime already does well.

The intended flow is:

> **status → targeted Project Map lookup when needed → current-source verification → native execution → durable recording only where useful**

That is the boundary the project should preserve as it grows.

## Documentation authority

For actual product behavior, source code, migrations and executable tests take precedence over prose documentation. Documentation that disagrees with executable behavior is a defect.

The point-in-time [independent audit of v0.14.0](docs/AUDIT.md) records confirmed
release blockers and their reproduction evidence. Future agents must verify
each finding against current source before treating it as open or resolved.
