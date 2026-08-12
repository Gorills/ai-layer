---
slug: architecture
description: Architecture design and change discipline for boundaries, dependencies, invariants, scalability, operability and evolutionary cost.
kind: core
keywords:
- architecture
- boundaries
- modules
- dependencies
- domain
- application
- infrastructure
- interfaces
- scalability
- ADR
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Software Architecture Skill

## Apply when

Use when a change introduces or moves a subsystem, creates a new dependency direction, changes ownership of data or behavior, adds a long-lived integration, or may make future change materially harder. Also use before large refactors and when a feature appears to require “just one exception” to existing boundaries.

## Core contract

- Architecture exists to control change cost, failure blast radius and ownership; do not optimize diagrams while the runtime dependency graph remains tangled.

- Start from the actual repository: package/module graph, entry points, data stores, queues, public APIs, deployment units and tests. Documentation is evidence, not proof.

- Define responsibilities in verbs and owned invariants. A boundary that cannot say what it owns is usually only a folder boundary.

- Keep domain decisions independent of transport, persistence, framework and vendor details where the product actually benefits from substitution or isolated testing.

- Dependencies should point toward stable policy. Adapters may depend on application contracts; core policy should not import HTTP handlers, ORM sessions or SDK clients.

- Prefer one canonical path for a business capability. Parallel flows that perform the same business operation are architectural debt even when each flow is individually clean.

- Make cross-boundary contracts explicit: inputs, outputs, errors, idempotency, transactions, ownership, compatibility and observability.

- Evaluate architecture against failure and evolution scenarios, not only the happy-path class diagram: retries, partial outages, schema evolution, backfills, scaling and rollback.

- Avoid abstractions without a demonstrated axis of change. A direct dependency is often safer than an interface invented only to satisfy a pattern.

- Record irreversible or expensive choices, rejected alternatives and migration constraints so later agents do not rediscover the same fork.

## Evidence to inspect

- Repository and package tree, imports between major modules, framework entry points and dependency-injection/composition roots.

- Database schema, migration history, ownership of tables/entities, transaction boundaries and code paths that mutate the same data.

- Public HTTP/RPC/event contracts, background workers, schedulers and external SDK boundaries.

- Existing ADRs, architecture documents and tests that encode invariants; verify claims against code before treating them as authoritative.

- Runtime topology: processes, containers, queues, caches, object storage, third-party services and deployment/rollback mechanics.

- Recent change history around the affected area to detect repeated coupling, workaround layers or unstable ownership.

## Decision rules

- If two modules must change together for most features, reassess whether the boundary represents real independent responsibility.

- If core logic requires framework request/response objects, ORM models or vendor SDK types, translate at the boundary unless the coupling is intentionally accepted and documented.

- If a new abstraction has only one implementation and no meaningful test or substitution benefit, prefer a concrete implementation until the variation is real.

- If the operation spans multiple durable systems, choose and document consistency semantics explicitly: local transaction, outbox/inbox, saga, compensation or accepted eventual inconsistency.

- If a new service is proposed only to separate code, prefer a module boundary first; distribution adds latency, partial failure, versioning and operations.

- If a compatibility shim is needed, give it an owner, removal condition and tests. Do not let transition code become the permanent architecture accidentally.

- If a change increases fan-out from a central module, check whether that module is becoming an orchestration god-object and split by responsibility rather than file size alone.

- If a design cannot explain rollback, observability and failure isolation, it is not implementation-ready.

## Workflow

1. Map the current capability end-to-end from entry point to durable side effects. Mark ownership, contracts and external dependencies.

2. State the problem and constraints in architectural terms: what must change, what must remain stable, and which qualities matter.

3. List at least two viable designs when the choice is consequential. Compare change surface, coupling, failure modes, data migration, operations and reversibility.

4. Choose boundaries and dependency directions; define the smallest contracts needed at each boundary before writing framework glue.

5. Plan migration in independently safe increments. Preserve a working system at each step and avoid flag-day rewrites unless the environment truly allows them.

6. Implement one canonical path and remove or quarantine superseded paths. Keep adapters thin and business decisions in their owner layer.

7. Verify with architecture/static checks plus behavioral tests that cross the new boundary and failure scenarios.

8. Re-read the diff as an architecture change: identify new dependencies, duplicated concepts, orphaned compatibility code and assumptions that need an ADR.

## Implementation patterns

- Ports/adapters are useful where external systems or persistence vary; they are not a requirement around every function.

- Application services coordinate use cases and transactions; domain objects/functions enforce business invariants; adapters translate protocols and persistence.

- Composition roots are the correct place to bind concrete infrastructure to abstract application contracts. Avoid hidden service locators in business code.

- Use anti-corruption layers when an external model would otherwise leak vendor vocabulary and constraints throughout the application.

- For modular monoliths, enforce import boundaries and data ownership as if modules might later separate, without paying distributed-system cost prematurely.

- For event-driven flows, define event meaning, producer ownership, schema evolution, delivery semantics and consumer idempotency before relying on events as a boundary.

- For read models, consciously separate query-optimized projections from write invariants instead of mutating denormalized copies ad hoc.

- Prefer explicit result/error contracts across boundaries over catching broad exceptions in outer layers and guessing what failed.

## Failure modes

- Folder-only architecture: modules are named domain/application/infrastructure but imports point everywhere. Correct the dependency graph, not the labels.

- Interface proliferation: dozens of one-method abstractions obscure flow without isolating volatility. Collapse abstractions that have no real boundary value.

- Service explosion: extracting deployables to solve code organization introduces network failure and operational burden. Reconsider a modular monolith.

- Shared database ownership: several modules mutate the same tables directly, making invariants ownerless. Assign mutation ownership and expose a contract.

- Dual business flows: a new implementation bypasses the existing pipeline for convenience. Integrate through the canonical flow or explicitly replace it.

- Transaction leakage: handlers or controllers manually coordinate partial writes across repositories. Move atomic use-case coordination to the owning application layer.

- Vendor model leakage: SDK/ORM types appear in core contracts and tests. Translate them at the adapter boundary.

- Big-bang refactor: architecture improvement cannot be deployed until every consumer changes. Introduce compatibility seams and migrate incrementally.

## Verification

- Draw or derive the post-change dependency graph and confirm forbidden inward-to-outward imports did not appear.

- Trace at least one success path, one validation failure, one infrastructure failure and one retry/duplicate path through the boundaries.

- Run architecture/static gates and tests that exercise contracts through realistic adapters where practical.

- Verify transaction scope and ownership for every durable mutation introduced or moved.

- Test compatibility with existing callers/events/data when a public or persisted contract changed.

- Confirm logs/metrics/events identify the owning capability and preserve correlation across asynchronous boundaries.

- Review deployment and rollback order, including schema compatibility and mixed-version behavior.

- Search for the old path, duplicate concepts and direct adapter access that should have disappeared.

## Completion criteria

- Every changed responsibility has one clear owner and a reason for its boundary.

- Dependency direction is intentional and enforceable by code structure or tooling, not only documentation.

- Cross-boundary data, error, consistency and compatibility semantics are explicit.

- The migration can be deployed and rolled back safely for the project's actual environment.

- No parallel business path or temporary compatibility layer was left without an explicit lifecycle.

- Behavioral, architecture and failure-path verification provide evidence for the design claims.

- Consequential decisions and rejected alternatives are recorded where future maintainers will find them.

## Related skills and escalation

- Use `legacy-change` when the main risk is changing poorly understood existing behavior.

- Use `api-contracts`, `database`, `data-consistency` and `external-integrations` for the corresponding boundary details.

- Use `security` whenever trust boundaries, privilege or sensitive data cross the proposed architecture.

- Escalate for human architectural approval when the choice creates an irreversible datastore, protocol, deployment or ownership commitment.
