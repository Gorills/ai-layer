---
slug: gamedev
description: Game runtime state, scenes/entities, input, lifecycle, performance, persistence,
  physics and gameplay-system implementation.
kind: domain
keywords:
- gamedev
- game
- gameplay
- scene
- entity
- input
- save
- frame
- physics
- animation
- inventory
- combat
- npc
- игра
- сцена
- персонаж
- сохран
- физик
- инвентар
---
# Game Development Skill

## Apply when
Gameplay systems, runtime scenes/entities, input, save data, animation/physics ownership, or frame-sensitive behavior are changed.

## Mandatory rules
- Keep canonical gameplay state independent from presentation when practical.
- Make scene/entity ownership and lifecycle explicit; avoid hidden cross-scene state.
- Route input through the engine/project action system, not hard-coded device keys.
- Keep per-frame/per-physics work bounded and avoid avoidable allocations or runtime asset loading on hot paths.
- Version persisted save/state formats once compatibility matters.

## Decision rules
- Prefer data/resources/configuration for reusable content; prefer code for behavior and invariants.
- Use a global singleton only for truly global lifecycle-owned services, not as a shortcut around ownership.
- Optimize only measured or structurally obvious hot paths; do not sacrifice clarity for hypothetical frame cost.

## Failure modes
Deep scene-tree coupling, frame-rate-dependent gameplay, duplicated state in UI and world nodes, editor-only assumptions at runtime, blocking asset loads in hot paths, and save schemas with no migration plan.

## Quality gates
- Representative runtime scene/flow is exercised.
- Input and lifecycle behavior is checked on the relevant devices/modes.
- Save/load or serialization changes have compatibility coverage where applicable.
- Performance-sensitive changes are measured or bounded by a defensible invariant.
