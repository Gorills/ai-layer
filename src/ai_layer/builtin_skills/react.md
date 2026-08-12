---
slug: react
description: React engineering for component identity, state ownership, effects, rendering, forms, context, async data and resilient composition.
kind: stack
keywords:
- react
- hooks
- state
- effect
- component
- context
- key
- render
- form
- suspense
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# React Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring React code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual React version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established React architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Treat render as a pure description from props/state/context; side effects belong in event handlers or effects only when synchronizing with an external system.

- State is tied to component position/identity; use stable keys based on entity identity and intentionally change key only when state reset is desired.

- Do not use effects to derive state that can be calculated during render; redundant state/effects create stale synchronization.

- Keep state as local as practical and lift/share it only to the nearest owner that needs to coordinate children.

- Never define component functions inside another component when identity preservation matters; nested definitions can reset state and hurt performance.

- Effect dependencies must reflect values used by the synchronization; do not suppress lint to preserve accidental behavior.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the React and toolchain versions.

- React/package version, renderer/framework (Next/Vite/etc.) and build/runtime mode.

- Component tree/state ownership, hook usage, contexts and server-state/query library.

- Effects with subscriptions/network/timers and component keys/identity.

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

- If an effect only updates state from other state/props, remove it and derive during render or update both from the same event.

- If a list item has editable/local state, key it by stable domain identity rather than array index when ordering can change.

- If context updates cause broad rerender and value is high-frequency, split contexts/state ownership before memoizing everything.

- If async server data has caching/revalidation needs, use the project's established server-state/framework data primitive rather than reimplementing cache in component state.

## Workflow

1. Detect React version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use controlled/uncontrolled form patterns consistently with the project's form library; preserve stable field identity for dynamic arrays.

- Custom hooks should package reusable stateful behavior, not hide arbitrary service-locator access or business logic.

- Use refs for imperative DOM/integration handles and mutable values that do not drive rendering; do not use them to bypass state model.

- Use memo/useMemo/useCallback only when measured or required for stable dependency/child identity, not as default.

- For subscriptions, timers and external widgets, effect setup must return cleanup and tolerate development lifecycle checks.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## State and effects

- Before adding state, ask whether the value can be calculated from current props/state/server data. Derived values belong in render/selectors.

- Before adding an effect, name the external system being synchronized: DOM API, network subscription, timer, widget, browser API. If none exists, an effect is often unnecessary.

- Events describe user/system actions; effects describe synchronization caused by rendering/state. Keep business mutations close to events/use-case hooks.

- State reset should be explicit through identity/key or owner state transitions, not incidental through conditional component definitions.

## Failure modes

- Effect loop/sync: effect mirrors props into state and causes extra/stale renders. Derive or restructure events.

- Index keys: reordered list carries state to wrong item. Use stable entity key.

- Nested component definition: state resets on parent render. Move definition to module/top scope.

- Context dump: one giant context carries unrelated mutable state and rerenders app. Split by ownership/change frequency.

- Stale closure workaround: dependency omitted to freeze old value. Fix lifecycle/data flow rather than suppressing lint.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run React/framework lint including hooks rules and type checks.

- Test component identity through reorder/add/remove and verify local state stays with correct entity.

- Exercise effect setup/cleanup under mount/unmount/remount and route changes.

- Use React DevTools/profiler only when performance claim is material and compare measured renders.

- Test async race/error/loading behavior using the actual project data layer.

- Run the project's canonical React formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual React version and architecture.

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
