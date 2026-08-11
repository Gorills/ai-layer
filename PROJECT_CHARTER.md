# Project Charter

## Product

Local AI Development Layer is a single-machine control plane for AI-assisted software engineering. It owns durable project identity, project memory/context, expert skills, durable Tasks, delegated worker provenance, verification evidence, observability, dashboard projections, host integrations, installation and upgrades.

The product is not a chat transcript and chat history is never authoritative workflow state.

## Three ownership layers

1. **Development repository** — this repository: source, tests, migrations, release tooling, CI-compatible gates, built-in runtime skills, maintainership rules and ADRs.
2. **Machine runtime/control plane** — installed immutable runtime, daemon, database, project registry, Task/Skill/Context/Verification engines, projections, host adapters and updater.
3. **Target projects** — user repositories. AI Layer implementation is never copied into them. Standard mode may install minimal generated host bridge files. Strict-private mode keeps AI Layer state external and removes those bridges.

Development governance belongs only to this repository. Runtime skills are engineering contracts for agents working on target projects; they are a separate product capability.

## Foundation invariant

Tasks are the atomic durable execution unit. A future Epic capability may schedule Tasks, but Task Engine must not own an Epic DAG, Epic planner or Epic scheduler.

## Simplicity invariant

AI Layer must remain the smallest system that reliably enforces the current product contract. The host/model interprets natural-language user intent; AI Layer supplies durable facts, tools and hard invariants.

Prefer deletion, reuse, native host capabilities and direct composition over new layers. Do not add phrase/intent classifiers, speculative routers, parallel mechanisms, generic workflow frameworks, state machines, persistence or compatibility abstractions for hypothetical future needs. A new abstraction is justified only by a concrete current problem and should reduce the net conceptual surface of the system.

## Non-goals of the pre-Epics foundation

This version intentionally does not implement Epic persistence, planning, scheduling, orchestration, Epic dashboard behavior, concurrent repository writers, distributed queues, microservices or a generic workflow language.

## Source of truth

For product behavior, source code, executable contracts, migrations and tests take priority over prose documentation. Documentation that disagrees with executable behavior is a defect.
