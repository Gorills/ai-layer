# ADR 0022 — Canonical current product improvement goal

## Status

Accepted for the current improvement program.

## Context

The repository had implementation-state documentation and an old version-specific roadmap, but no single durable statement of the user outcome currently being pursued. Agents could optimize a local feature, maximize Task/event volume or follow an obsolete milestone without understanding the intended multi-project human and agent experience.

Target behavior and implemented behavior also need separate documents. Combining them would either misrepresent planned behavior as current or make the desired outcome disappear whenever release state is updated.

## Decision

Root `PRODUCT_GOAL.md` is the canonical outcome and Definition of Done for the current improvement program. Root `ROADMAP.md` contains sequencing only. `CURRENT_STATE.md` continues to describe implemented and verified source state. Repository bootstrap requires contributors and agents to read all three roles explicitly.

`PRODUCT_GOAL.md` is development governance: it is allowed in the repository root but excluded from the installable runtime archive together with other maintainer-only material.

The goal prioritizes trustworthy portfolio observability, lightweight WorkItem lifecycle, optional managed assurance, useful Project Intelligence, explicit coverage/assurance, Project Map closure, privacy, and strict separation of development source, machine runtime and target-project artifacts. Success is measured by durable useful outcomes and time-to-understanding, not Task/tool/event counts.

## Consequences

- Future agents can evaluate proposed work against one stable end-to-end outcome.
- Planned behavior is not presented as already implemented.
- Roadmap phases may change without silently redefining product success.
- Local optimizations that increase ceremony, fabricate visibility or pollute target repositories are explicitly outside the goal.
