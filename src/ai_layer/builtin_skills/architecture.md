---
slug: architecture
description: Minimal-change architecture discipline for repository-level design and
  refactoring.
kind: core
keywords:
- architecture
- design
- boundary
- module
- dependency
- refactor
- abstraction
- ownership
- replace
- introduce
- restructure
- архитектур
- рефактор
- границ
- заменить
- внедрить
---
# Architecture Skill

## Apply when
Architecture, module boundaries, durable abstractions, dependency direction, public contracts, or non-trivial refactoring are part of the task.

## Mandatory rules
- Reconstruct the current boundary and caller flow from source before proposing a new one.
- Current source, project rules, and recorded project decisions outrank this generic skill.
- Prefer the smallest coherent seam that preserves existing callers and ownership.
- Do not create a parallel mechanism when an existing extension point can satisfy the requirement.
- New dependencies, services, abstractions, or persistence models require a concrete present need, not speculative future value.
- Treat owner growth as an architecture signal. If the current owner already mixes responsibilities or is at/near a repository maintainability limit, extract the smallest coherent seam before adding more behavior.
- Compatibility facades may preserve imports and route calls, but they must not become a second owner for business logic.
- Do not introduce internal dependency cycles, including cycles hidden behind local/lazy imports.
- If the repository exposes an architecture/maintainability gate, run it before completion. Do not weaken its thresholds or ratchets as part of an ordinary feature/fix task; a policy change requires an explicit architecture scope.

## Decision rules
- If the path is already determined by current architecture, extend it rather than redesigning it.
- If multiple durable approaches are genuinely plausible and the choice affects API/provider/auth/concurrency/persistence, check historical decisions before choosing.
- If a change crosses more than one ownership boundary, identify why; split unrelated cleanup from the requested change.
- "Minimal change" never means "append to the existing god module". Prefer a bounded extraction that preserves the public contract when that prevents further structural debt.

## Failure modes
Parallel flows, god modules, hidden circular dependencies, broad rewrites for local features, abstractions with one speculative caller, and silent public-contract drift.

## Quality gates
- Entry points, owner module, dependencies, and compatibility impact are identified.
- Failure/rollback or migration behavior is considered where relevant.
- Tests verify behavior at the affected boundary, not only internal implementation.
- Existing oversized owners do not silently grow; repository ratchets/architecture checks remain green.
- Dependency direction remains acyclic and compatibility facades remain thin.
- Completion states what changed and what was actually verified; assumptions remain assumptions.
