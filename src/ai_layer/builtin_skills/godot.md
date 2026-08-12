---
slug: godot
description: Godot engineering for scenes, nodes, resources, signals, lifecycle, physics, input, autoloads and performance-conscious project structure.
kind: stack
keywords:
- godot
- godot 4
- gdscript
- scene
- node
- resource
- signal
- autoload
- physics
- inputmap
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Godot Engine Skill

## Apply when

Use when implementing, reviewing or refactoring Godot Engine code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Godot Engine version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Godot Engine architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use scenes as reusable composed objects/levels/UI units and scripts for behavior; do not turn every concept into a global singleton or one mega-scene.

- Keep node ownership/lifecycle explicit: cache required child references deliberately and disconnect/cleanup external subscriptions when lifetime differs.

- Use signals for decoupled event notification across ownership boundaries, but avoid global signal buses that hide every dependency.

- Use `_physics_process` for physics-timestep movement/physics interactions and `_process` for frame/render-related updates when needed.

- Use InputMap semantic actions rather than hardcoded physical keys/buttons across gameplay code.

- Resources are data assets and may be shared; do not mutate template `Resource` instances as per-entity runtime state unless duplication/ownership is intentional.

- Use autoloads only for truly process-wide services/state; scene-local systems should stay with scene ownership.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Godot Engine and toolchain versions.

- `project.godot`, engine version, renderer/input/physics settings and addon list.

- Scene tree ownership, reusable scenes/resources, autoloads and signal connections.

- `_process`/`_physics_process` callbacks, physics bodies/collision layers and InputMap actions.

- Existing tests around the same capability and canonical CI/quality commands.

- Framework/language configuration that changes defaults, strictness, routing, build, serialization or runtime behavior.

- Official version-matched documentation/release notes for any uncertain or recently changed API.

## Decision rules

- If existing code has a canonical wrapper/service/component pattern, extend it rather than introducing a parallel framework idiom in one feature.

- If a convenience API hides database/network/filesystem work, make the I/O boundary and failure/transaction behavior explicit before using it in loops or critical paths.

- If a type/validation escape is proposed solely to silence tooling, fix the model or narrow the unsafe boundary and document why it is unavoidable.

- If a dependency can be replaced by a small use of the standard/framework library, prefer the simpler maintained surface unless the dependency adds proven value.

- If official guidance differs across versions, follow the pinned project version and record upgrade implications rather than coding against latest docs blindly.

- If a framework hook/lifecycle method changes global behavior, locate all registration/composition points and test startup/shutdown/error behavior.

- If a node needs a sibling/parent path deep across scene structure, inject/export/reference through owner or signal rather than fragile absolute paths.

- If the same scene instantiation should have unique mutable data, duplicate/create runtime state instead of mutating a shared `.tres` template.

- If dozens/hundreds of actors run identical expensive `_process`, reduce update cadence or centralize/spatially schedule based on gameplay need.

- If communication only flows to an owner/parent, a direct method may be clearer; use signals when emitter should not know receivers.

## Workflow

1. Detect Godot Engine version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use typed GDScript where project uses it to catch node/resource/data shape errors earlier.

- Use `@export` for editor-configurable dependencies/data with validation rather than `get_node` paths scattered throughout scripts.

- Use `PackedScene` composition for reusable entities/components and keep scene root API small.

- Use groups for broad categorization/query only when membership semantics are clear; avoid global per-frame group scans at scale.

- Use AnimationPlayer/AnimationTree for presentation while keeping critical gameplay state transition ownership explicit.

- Free/queue_free nodes through clear owners and guard async/tween/signal callbacks from accessing invalid freed instances.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Scene and node ownership

- A reusable scene should expose a small behavioral API and own its internal child arrangement. External scripts that reach deeply into child paths make scenes brittle.

- Prefer parent/owner configuring children and children emitting intent/events upward when that keeps dependencies directional.

- Use autoloads for global services such as save/settings/audio coordination only when their lifetime genuinely matches the whole process.

- Scene changes must consider queued deletion, asynchronous callbacks and references held by global services.

## Performance and simulation

- Profile before replacing ordinary nodes with custom data/ECS-style structures; Godot nodes are appropriate until measured counts/update patterns make them costly.

- Separate high-frequency movement from lower-frequency decision/perception logic for many NPCs.

- Use physics queries/collision layers intentionally; broad masks and constant shape queries across hundreds of actors can dominate frame time.

- Load/preload/stream assets based on scene transition and memory budget rather than preloading the entire project.

## Failure modes

- God object autoload: every system accesses mutable singleton state. Move scene/domain ownership local and inject narrow global services.

- Shared Resource mutation: one NPC/item edit changes all instances. Duplicate runtime data or separate config/state.

- NodePath fragility: scene refactor breaks deep `$../../..` lookups. Use owner/exported references/composition.

- Signal leak/ghost callback: external emitter outlives node and calls freed/stale object. Manage connection lifecycle.

- All NPC logic in `_process`: population scales poorly. Stagger/event/spatial update.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run/import project under the detected Godot version and inspect parser/runtime warnings.

- Play representative scenes through load/unload/reload and verify no orphan/leaked callbacks/nodes.

- Test InputMap actions with required keyboard/gamepad devices.

- Use Godot profiler/monitor for frame time, physics, node count and memory in representative entity scenes.

- Verify shared Resource instances are not mutated unexpectedly across entities.

- Run the project's canonical Godot Engine formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Godot Engine version and architecture.

- No parallel framework pattern or dependency was introduced without a clear reason.

- Types/validation/error/resource semantics are explicit at important boundaries.

- Version-sensitive behavior is source-backed and regression-tested where material.

- Stack-specific and repository-wide quality gates pass.

- The final diff contains only intentional dependency/configuration changes.

## Related skills and escalation

- Combine with the relevant domain skill (`backend`, `frontend`, `database`, `design`, `security`, `testing`) for behavior beyond stack mechanics.

- Use `source-first` for uncertain/version-sensitive APIs and `compatibility` for major upgrades.

- Use `verification` for honest completion evidence.

- Escalate when the required solution depends on undocumented runtime behavior or a major version upgrade outside scope.
