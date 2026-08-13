# Roadmap — current improvement program

The canonical target outcome is [PRODUCT_GOAL.md](PRODUCT_GOAL.md). This file contains sequencing only; it must not redefine the product goal or claim planned behavior as implemented. Verified implementation state remains in [CURRENT_STATE.md](CURRENT_STATE.md).

## Phase 0 — truthful foundations

- Separate WorkItem, managed Task/Epic and RuntimeEvent identities.
- Stop deriving “agent working” from open Tasks or MCP bridges.
- Deliver effective project rules through the normal startup path.
- Make structural and semantic Project Map quality visible separately.
- Establish one safe durable event journal and correlation spine.
- Restrict Work/check/repository evidence to bounded nonsecret metadata.

## Phase 1 — durable Work history and Dashboard

- Provide Work list/detail read models and stable API contracts.
- Build portfolio Now / Needs attention / Recently completed views.
- Add a unified milestone-first RuntimeEvent timeline with deterministic cursor pagination and filters.
- Display host sessions, subagents, managed workers and MCP bridges separately.
- Expose heartbeat, lease, staleness, observability coverage and assurance.
- Make Project Map disposition and semantic coverage first-class attention signals.

## Phase 2 — host integration coverage

- Add capability-negotiated adapters for official work/session/tool/subagent hooks.
- Propagate stable host session, turn, actor, work and correlation identities.
- Record inferred repository deltas only as unattributed evidence.
- Publish explicit per-host coverage contracts and black-box tests.

## Phase 3 — target-project and installation boundary

- Move mutable canonical project runtime state out of standard target repositories.
- Define minimal standard-mode and zero-footprint artifact contracts.
- Add a declarative installed-artifact ledger with desired hashes and ownership.
- Make install/update/repair/uninstall symlink-safe, phased, restartable and recoverable.
- Prevent global policy/rule installation from affecting unrelated repositories.

## Phase 4 — retention, scale and field acceptance

- Add retention classes, heartbeat rollups and diagnostic cleanup.
- Remove portfolio N+1 reads and validate query/latency budgets at representative scale.
- Exercise restart/replay, mixed-version migration and partial-failure recovery.
- Run supported-host black-box journeys for ordinary Work, managed Task/Epic, Project Map closure, privacy and multi-project Dashboard use.
- Measure the success metrics from `PRODUCT_GOAL.md` and adjust only from field evidence.

Each phase must leave one canonical path and pass repository quality gates. Later phases do not justify weakening correctness, privacy or truthful-state guarantees in earlier phases.
