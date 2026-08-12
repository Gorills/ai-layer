---
slug: gamedev
description: Game engineering for deterministic gameplay state, frame budgets, simulation boundaries, save compatibility, input, content data and testable systems.
kind: domain
keywords:
- game development
- gameplay
- simulation
- frame budget
- save game
- input
- entity
- state machine
- content pipeline
- profiling
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Game Development Systems Skill

## Apply when

Use for gameplay systems, player/NPC behavior, inventory/quests/combat, input, save/load, world simulation, game loops and performance-sensitive runtime code. Combine with the engine-specific skill (`godot` when applicable) rather than embedding game design invariants in scene callbacks.

## Core contract

- Separate simulation/gameplay state from presentation where practical. Visual nodes/animations should reflect authoritative game state rather than become the only source of truth.

- Treat frame time as a budget. Avoid unbounded per-frame scans, allocations, pathfinding, serialization or network work; schedule/batch/cache based on measurement.

- Use explicit state machines or similarly constrained transitions for gameplay with meaningful states; scattered booleans permit impossible combinations.

- Input expresses player intent, not direct mutation of every subsystem. Map devices/actions through one input layer so keyboard/gamepad/remapping can share behavior.

- Persist stable semantic save data, not raw engine object graphs. Version save schemas and provide migration/default behavior for older saves.

- Game content should be data-driven when designers/large content sets need iteration, while rules/invariants remain code-owned.

- Randomness that affects replay/testing/network determinism should use owned RNG/state/seed rather than global uncontrolled random calls.

- AI/NPC systems need bounded perception/update cadence; not every agent needs full logic every frame.

- Physics, animation and rendering each have their own update/lifecycle semantics; do not mutate shared state from arbitrary callbacks without ownership.

- Profile real gameplay scenes with representative entity/content counts before optimizing architecture from intuition.

## Evidence to inspect

- Main loop/update callbacks and entity/NPC counts in representative scenes.

- Gameplay state ownership, state machines, event/message/signals and presentation binding.

- Input action map and device-specific code.

- Save schema/versioning and content resource/data formats.

- Physics/collision layers, pathfinding/navigation and AI update scheduling.

- Profiler traces for CPU frame, GPU/render, memory/allocation and loading hitches.

## Decision rules

- If a system scans all entities every frame but information changes infrequently, update on events or staggered cadence.

- If gameplay state is encoded in many flags, model explicit mutually exclusive states/transitions.

- If an animation callback is the only place applying important business/gameplay result, decide whether event timing is presentation or authoritative simulation and make it testable.

- If player action must work across devices, bind to semantic input actions rather than hardcoded key codes.

- If save format includes engine paths/object internals, map to stable IDs/data structures and version them.

- If randomness must reproduce bugs or synchronize peers, own the seed/stream and avoid non-deterministic iteration/order.

- If loading asset/content causes frame hitch, move preload/streaming/budgeted load based on actual runtime platform constraints.

- If NPC count grows, use LOD for simulation/perception/animation as well as rendering.

## Workflow

1. Define the gameplay invariant/state and player-visible behavior independent of engine callbacks.

2. Map update frequency and owners: input, simulation tick, physics, animation/presentation and background loading.

3. Choose explicit data/state-machine/event boundaries and stable IDs for entities/content.

4. Implement the simplest correct system with bounded per-frame work and engine-idiomatic integration.

5. Add save/load/version behavior if new durable state is introduced.

6. Test gameplay rules in isolation where possible, then engine/runtime interactions in representative scenes.

7. Profile CPU/GPU/memory/loading using realistic entity/content counts.

8. Play through failure/edge states: pause, reload, scene transition, death/despawn, disconnect/device change as relevant.

## Implementation patterns

- Use semantic command/input actions and route them to player/controller logic rather than querying raw keys throughout gameplay code.

- Use state machines with validated transitions for character/NPC/quest/combat lifecycle.

- Use stable entity/content IDs and registries rather than persistent references to transient scene nodes.

- Use object pooling only where profiling shows allocation/instantiation pressure and reset semantics are provably correct.

- Use spatial queries/partitioning/event subscriptions instead of global entity scans for perception/proximity systems.

- Stagger expensive AI decisions across frames and separate high-frequency locomotion from low-frequency planning.

- Version save data with explicit migration/defaulting and test old saves as fixtures.

- Separate config/content resource data from mutable runtime state so one instance cannot accidentally mutate shared templates.

## Failure modes

- Everything in `_process`/Update: per-frame loops grow with content and frame time collapses. Use event/cadence/spatial design.

- Flag soup: `is_attacking`, `is_dead`, `is_stunned`, etc. allow contradictory states. Model transition state.

- Raw input keys everywhere: remapping/gamepad breaks. Use action mapping.

- Save raw nodes: scene refactor corrupts saves. Serialize stable semantic data/version.

- Shared resource mutation: editing runtime instance changes all entities using same template. Separate immutable config/mutable state.

- Premature pooling/ECS rewrite: complexity added without profile evidence. Measure bottleneck first.

- AI full tick for every NPC: population scaling is quadratic/unbounded. Apply simulation LOD/staggering/spatial limits.

- Presentation authority: missing animation signal prevents core state transition. Define authoritative timing and fallback.

## Verification

- Run rule/state tests for valid and invalid transitions independent of graphics where feasible.

- Test keyboard/mouse/gamepad action mapping and remap flow for relevant player actions.

- Load representative old save fixtures and round-trip current save/load without losing invariants.

- Profile representative worst-case scene/entity counts and record CPU/GPU/memory bottlenecks.

- Exercise pause/resume, scene reload/transition and entity spawn/despawn cleanup.

- Test deterministic seeded behavior when reproducibility is a requirement.

- Inspect per-frame allocation/log spam and expensive global queries in profiler.

- Playtest realistic edge state sequences rather than only scripted happy path.

## Completion criteria

- Gameplay state has explicit ownership and cannot enter known impossible combinations.

- Per-frame work is bounded/profiler-validated for target scale.

- Input is semantic and device-independent within project requirements.

- Durable game state has stable IDs/schema/version compatibility where needed.

- Presentation and engine callbacks cannot silently become untestable single points of gameplay truth.

- Representative runtime profiling and playthrough evidence support quality claims.

## Related skills and escalation

- Use `godot` for engine-specific nodes/resources/signals/physics practices.

- Use `architecture` for subsystem boundaries, `data-consistency` for multiplayer/shared-state semantics and `testing` for deterministic rules.

- Use `design`/`accessibility` for game UI and controls where applicable.

- Escalate when networking/deterministic lockstep/anti-cheat requirements materially change simulation architecture.
