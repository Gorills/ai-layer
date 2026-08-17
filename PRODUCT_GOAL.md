# Current Product Goal — trustworthy multi-project AI development control plane

## Status and authority

This document defines the target outcome of the current AI Layer improvement program. It describes the product we are trying to reach, not the behavior already implemented today.

- `PRODUCT_GOAL.md` answers **what outcome must exist**.
- `ROADMAP.md` answers **in what order we intend to reach it**.
- `CURRENT_STATE.md` answers **what is implemented and verified now**.
- Source, migrations and executable tests remain the authority for current behavior.

An implementation is not complete merely because a schema, MCP tool or Dashboard panel exists. The end-to-end human and agent journeys in this document must work truthfully across restart, reconnect and multiple projects.

## One-sentence outcome

AI Layer must become a local portfolio control plane that gives a human a trustworthy, durable view of what AI agents are doing across many projects, while giving agents compact project context, navigation and continuation without forcing every edit through a heavyweight workflow or polluting target repositories with AI Layer runtime state.

## Primary users and jobs

### Human portfolio owner

The owner may maintain many unrelated projects and must be able to answer quickly:

- What work is happening now, in which project, and for what user-visible goal?
- Which work is blocked, stale, failed, awaiting a decision or missing Project Map closure?
- Which agent/session performed the work, and how certain is AI Layer about that attribution?
- What meaningful milestones, code areas and checks were recorded?
- What completed recently, when did it finish, and what was the outcome?
- Is Project Map structurally fresh and semantically useful, or does the project still lack durable navigation knowledge?
- Is a displayed signal real host observation, an agent report, an inference, or only control-plane activity?

The owner must not need to inspect chat history, MCP logs, Git status in every repository or raw database rows to reconstruct this picture.

### Coding agent

An agent entering a registered target project must be able to:

- recover the current bounded focus and project rules cheaply;
- find likely code locations without rescanning the whole repository every time;
- distinguish current source truth from Project Map breadcrumbs and reviewed Knowledge;
- record one substantive user request with minimal lifecycle ceremony;
- use managed Tasks/Epics only when their stronger assurance is valuable;
- leave a durable terminal outcome, verification summary and explicit Project Map disposition;
- continue safely after chat, process or host restart.

## Product model

AI Layer must preserve three separate concepts.

1. **WorkItem** — one substantive user-visible unit of work. It is the default durable identity for ordinary host-native development.
2. **Managed Task / Epic** — optional strict assurance workflows for review, findings, verification, approvals, planning and recovery. They may link to WorkItem but do not replace it.
3. **Activity / RuntimeEvent** — append-only evidence and milestones produced while work happens. Events explain a WorkItem; they are not the WorkItem itself.

The system must not create a managed Task for every read, command, edit or tool call. Short substantive work should normally require one begin record and one terminal record. Progress events are reserved for meaningful phase changes, results and blockers.

Tiny read-only interactions may remain unmaterialized when no durable continuation or portfolio value exists. The product should optimize useful history, not event volume.

## Required human experience

### Portfolio Dashboard

The default view must prioritize:

1. **Now** — genuinely live WorkItems supported by non-stale observed/reported AgentRuns.
2. **Needs attention** — blocked/stale work, failures, human decisions, missing terminal state, verification failures and pending Project Map disposition.
3. **Recently completed** — durable outcomes across projects in deterministic chronological order.

Every Work card must show the bounded goal, project, status, last meaningful milestone, actor/session identity where available, attribution assurance, observability coverage, linked Task/Epic, checks, repository delta summary and Project Map disposition.

### Durable Work detail

Opening a WorkItem must show:

- start, meaningful progress and terminal outcome with timestamps;
- root-agent and subagent runs separately, including heartbeat/staleness and coverage;
- linked Task/Epic milestones without duplicating their internal histories;
- reviewed and changed project-relative paths;
- bounded safe check summaries and repository delta metadata;
- Project Map reconciliation/no-change/not-applicable/deferred evidence;
- gaps explicitly labelled when the host could not provide full observation.

### Unified timeline

The activity view must read the durable RuntimeEvent journal, use deterministic cursor pagination, and support filters for project, date, WorkItem, Task, Epic, actor, event type, status, importance and assurance.

Meaningful milestones are the default. Tool-level operations and heartbeats are collapsible diagnostic detail. The UI must never expose raw prompts, chain-of-thought, source bodies, secrets or unredacted command/output evidence by default.

### Honest agent identity

Dashboard must display these as separate read models:

- host agent sessions and subagents;
- managed Task workers and their leases;
- MCP bridges/processes.

An open Task or active MCP bridge alone must never be presented as proof that an agent is currently implementing work. Unsupported hosts must visibly report `control-plane only` or another truthful coverage level.

## Required agent experience

### Agent-effort design principle

Agents report user intent and genuinely new facts. AI Layer derives mechanics, identifiers, links and state that the control plane already owns. One user intent should map to one obvious primary tool; agents should not mirror backend state or perform bookkeeping that AI Layer can safely infer or repair.

For a new request, existing durable focus resumes first. With no active focus, an explicit user request for a managed Task or the standard Task protocol enters `task_create` directly; ordinary substantive work defaults to `work_begin`; tiny one-shot Q&A may stay unmaterialized. If a managed Task needs a backing WorkItem for portfolio history, AI Layer creates or links it automatically. Add agent ceremony only when the backend cannot safely resolve the ambiguity itself.

### Cheap startup and continuation

`project_status` must provide a bounded current-focus surface: project identity, effective rules, WorkItem continuation, optional managed Task/Epic focus, repository state and structural/semantic Project Map freshness. It must not require loading a giant legacy memory payload.

When code location is unknown, Project Map search should provide ranked metadata breadcrumbs. Agents must inspect current source before editing or making code-truth claims.

### Lightweight Work lifecycle

Supported hosts should make the following lifecycle reliable and low-friction:

```text
work_begin
  -> optional meaningful work_checkpoint(s)
  -> work_complete | work_fail | work_interrupt | work_abandon
```

The lifecycle must be idempotent, correlate one host/session/work identity across transports and events, survive restart, and never become per-edit permission gating.

Host adapters should use official lifecycle/tool/subagent hooks where available. A filesystem or Git observer may report an unattributed repository delta, but it must never invent which agent caused it.

### Project Map closure

Substantive terminal work must carry an explicit disposition:

- `reconciled` with inspected scope and durable reconciliation evidence;
- `checked_no_change` with inspected scope and factual reason;
- `not_applicable` with reason;
- `deferred` with visible follow-up reason;
- `pending`, which remains an attention signal rather than silently implying completion.

Semantic Project Map rows must retain WorkItem or managed Task provenance. Structural freshness and semantic coverage are separate metrics and must both be visible.

## Source, machine runtime and target-project boundary

The product has three operational layers and must keep them explicit:

1. **Development repository** — AI Layer source, tests, migrations, release artifacts and governance.
2. **Machine runtime** — installed immutable application, database, registry, generated runtime state, logs, sessions and host integration state.
3. **Target projects** — user source repositories being developed with agent assistance.

Canonical AI Layer state belongs to the machine runtime, keyed by stable project identity. A normal target repository must not accumulate AI Layer sessions, events, tasks, memory databases, logs or other mutable runtime state.

Any target-project artifact must be minimal, declarative, attributable to an explicit host integration, reversible and protected from overwriting user-authored content. External/strict-private operation should support a zero-footprint target repository where the host permits it.

Install, upgrade, repair and uninstall must operate from a declarative artifact ledger with desired versions/hashes, symlink-safe writes, restartable phases and recovery after partial failure. Updating AI Layer must not silently dirty every registered repository or delete unrelated user files.

Project-specific rules must be delivered through the normal project-status/bootstrap path with project scope. Global installation must not impose project-specific behavior on unrelated repositories.

## Truth, privacy and retention

Every displayed assertion must state or imply a defensible assurance class, such as:

- `ai_layer_observed`;
- `host_reported`;
- `agent_reported`;
- `inferred_unattributed`;
- `requested_unverified`.

Coverage and assurance are different: a host can report a lifecycle accurately while still lacking tool-level coverage.

Durable milestones and terminal outcomes must survive beyond short diagnostic retention. High-volume operations and heartbeats must have bounded retention/rollups. Raw diagnostic evidence must be opt-in, redacted, access-limited and short-lived.

No feature may require storing chain-of-thought. Prompts, source bodies, arbitrary tool results, secret-bearing environment values and raw command output are excluded from the default human journal.

## Reliability and scale expectations

- Mutating lifecycle calls are idempotent and safe under delivery retry.
- Human-facing project-local Work identifiers are concurrency-safe.
- Events share correlation, causation, work/session and actor identity across supported boundaries.
- Read models are restart-safe and rebuildable from canonical durable state where promised.
- Portfolio queries avoid per-project N+1 database access and remain bounded as project/event counts grow.
- Timeline pagination has deterministic `(occurred_at, event_id)` semantics without duplicates or skips under concurrent inserts.
- Missing database, host hooks or telemetry degrade to an explicit unavailable/partial state rather than fabricated success.

## Definition of Done for the current improvement program

The program is complete only when all of these journeys pass on supported environments:

1. **Ordinary native work without Task:** after restart, Dashboard shows goal, start, meaningful milestones, terminal result, timestamps, actor/coverage, changed-path and check summaries, repository delta and Project Map disposition. No managed Task was required.
2. **Managed work:** the same WorkItem links to a Task/Epic once; strict stage/review/finding/verification guarantees remain intact and milestones are not duplicated.
3. **Unsupported host:** Dashboard clearly reports partial/control-plane-only coverage and never claims an agent is working based only on an open Task, MCP process or repository delta.
4. **Project Map truth:** structural fresh plus zero semantic coverage is rendered as zero semantic coverage; terminal work cannot imply reconciliation without disposition evidence.
5. **Durable portfolio history:** a human can filter and inspect work completed more than seven days ago across many projects without reading raw logs.
6. **Privacy:** default APIs/UI exclude prompt, source, chain-of-thought, raw results and secret-bearing command/output fixtures; diagnostic detail is explicitly gated and expires.
7. **Target repository cleanliness:** standard and zero-footprint modes meet their documented artifact contracts; ordinary runtime activity does not dirty target Git worktrees.
8. **Lifecycle operations:** install/update/repair/uninstall are manifest-driven, symlink-safe, restartable and verified against partial failure and forgotten/unregistered targets.
9. **Quality:** unit, contract, real PostgreSQL/migration, privacy, restart/replay, concurrency and multi-project performance tests pass, followed by supported-host black-box acceptance.

## Success measures

Measure product usefulness rather than ceremony volume:

- share of substantive work with a durable terminal outcome;
- invisible-work and unattributed-delta rate by host;
- stale WorkItem rate and time to resolution;
- Project Map disposition rate and semantic current coverage;
- correlation join rate across Work/Run/Event/Task/Epic;
- time for a new agent to locate relevant source and make a verified first edit;
- user corrections caused by stale or misleading context;
- portfolio time-to-answer: “what happened, what is blocked, and what changed?”

Raw Task count, tool-call count and event volume are not success metrics.

## Explicit non-goals

- Replacing the host coding agent runtime.
- Requiring a managed Task for every action or file edit.
- Capturing hidden reasoning or chain-of-thought.
- Claiming full host visibility where no official hook exists.
- Storing source bodies as Project Map or activity history.
- Building a generic distributed workflow engine, message broker or multi-writer repository scheduler without demonstrated need.
