# Project Charter

## Product

Local AI Development Layer is a single-machine **Project Intelligence + Durable Work State + Observability** control plane for AI-assisted software engineering. It helps capable host agents avoid rediscovering project structure and prior work while preserving durable engineering state across chats, models and IDEs.

It owns project identity, metadata-only Project Map indexing, reviewed Project Knowledge, Decisions, durable Tasks and Epics, optional managed review/verification workflows, expert skill distribution, observability, dashboard projections, host integrations, installation and upgrades.

The host runtime (Cursor, Codex, Claude Code, Antigravity or another capable coding agent) remains the normal execution engine for reading source, editing, shell commands, tests, native code search, model selection and native subagents.

Chat history is never authoritative durable state, and AI Layer indexes never replace current repository source as code truth.

## Three ownership layers

1. **Development repository** — this repository: source, tests, migrations, release tooling, CI-compatible gates, built-in runtime skills, maintainership rules and ADRs.
2. **Machine runtime/control plane** — installed immutable runtime, daemon, database, project registry, Project Intelligence, Task/Epic/Skill/Verification capabilities, projections, host adapters and updater.
3. **Target projects** — user repositories. AI Layer implementation and managed state are not copied into them. Standard attachment is zero-footprint and uses global host integration plus machine-side project state; strict-private adds provenance restrictions and its Git privacy guard. The legacy `external` mode remains a compatibility spelling for the same zero-footprint attachment model.

Development governance belongs only to this repository. Runtime skills are engineering contracts for agents working on target projects; they are a separate product capability.

## Project Intelligence invariant

AI Layer should make already-learned project structure cheaper to reuse than to rediscover.

The read channels have distinct jobs:

- `project_status` — what is happening now: cheap continuation state, current Task/Epic focus, Git/worktree state and index freshness;
- `project_search` — where to look: metadata-only paths, symbols, imports, purposes and related tests;
- `knowledge_search` — what reviewed project facts/invariants are already known;
- `decision_search` — why consequential architectural choices were made.

Project Map stores breadcrumbs, not source bodies. Current repository source remains authoritative and must be inspected before code-truth claims or edits.

## Durable work invariant

Tasks and Epics are first-class durable work records. They preserve goals, stages, findings, verification, approvals, plans and continuation across chats.

They are **not a universal permission layer for every repository action**. Ordinary engineering defaults to host-native execution after project state/navigation retrieval. `task_next` and `epic_next` become authoritative when an existing managed workflow is resumed or managed/strict execution is explicitly selected.

Strict managed Task capabilities remain available where their guarantees add value: independent IMPLEMENT/REVIEW/FIX boundaries, read-only review/discovery, worker provenance, adoption of pre-existing changes, review sandboxes, findings, remediation caps and verification evidence.

Epics remain the durable outer contract/planning/integration layer over Tasks rather than a second implementation engine.

## Native-host invariant

Prefer native host capabilities over reimplementing an agent runtime. AI Layer must not globally disable native reading, editing, search, tests or subagents merely to force its own lifecycle.

Agent Skills are published into supported hosts and selected through host-native relevance/progressive disclosure. AI Layer may provide authoritative skill content and observability without centrally deciding every activation.

## Economy invariant

The optimization target is the **smallest total cost to a verified accepted engineering result**, not the smallest individual prompt and not maximum ceremony.

A control-plane call is justified when it reduces uncertainty, avoids repeated discovery, restores durable state or supplies evidence that the host would otherwise reconstruct. Do not make optional Project Knowledge, skill retrieval or workflow transitions mechanical startup overhead.

Telemetry must distinguish measured facts from estimates. Host-hidden context/model selection/billing must never be presented as verified cost data when AI Layer cannot observe it.

## Simplicity invariant

AI Layer must remain the smallest system that reliably provides Project Intelligence, durable state and useful verification/observability. The host/model interprets natural-language user intent; AI Layer supplies durable facts, navigation shortcuts and hard invariants only where those invariants have a concrete payoff.

Prefer deletion, reuse, native host capabilities and direct composition over new layers. A new abstraction is justified only by a concrete current problem and should reduce repeated work or net conceptual surface.

## Source of truth

For product behavior, source code, executable contracts, migrations and tests take priority over prose documentation. Documentation that disagrees with executable behavior is a defect.
