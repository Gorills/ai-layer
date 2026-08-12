---
slug: svelte
description: Svelte engineering for reactive state, runes or legacy reactivity, stores, component contracts, effects and lifecycle-safe rendering.
kind: stack
keywords:
- svelte
- sveltekit
- runes
- store
- reactivity
- component
- load
- actions
- transition
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Svelte Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring Svelte code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Svelte version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Svelte architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Match the reactivity model of the pinned Svelte version; do not mix runes/legacy patterns from memory without version evidence.

- Keep derived values derived and effects for true synchronization with external systems; avoid effect chains that mirror state.

- Respect SSR/browser separation: code touching `window`, DOM or browser-only storage must execute only in browser lifecycle/guards.

- Use SvelteKit load/actions/form mechanisms consistently with project routing/data architecture rather than duplicating client fetch/state.

- Keep shared stores for genuinely shared state; component-local interaction state stays local.

- Preserve component identity with keyed blocks only when intentional reset/recreation semantics are desired.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Svelte and toolchain versions.

- Svelte/SvelteKit version and whether the project uses runes-era or legacy reactive syntax.

- Component props/state/derived/effect usage, stores and route load/actions.

- SSR/browser boundaries, lifecycle and form/action behavior.

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

- If version is Svelte 5+, verify runes APIs from official docs before translating older `$:`/store patterns automatically.

- If data belongs to the route/server, prefer SvelteKit's established load/action boundary rather than fetching the same source again in arbitrary components.

- If code must run during SSR and browser, isolate browser-only capabilities and make hydration output deterministic.

## Workflow

1. Detect Svelte version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use derived reactive constructs for computed state and effect cleanup for subscriptions/listeners/timers.

- Use form actions/progressive enhancement when the project follows SvelteKit server mutation patterns.

- Keep serializable route data explicit across server/client boundary.

- Use actions for reusable DOM behavior with proper update/destroy lifecycle.

- Avoid giant writable stores containing unrelated app state; split by ownership.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Version-pattern mismatch: Svelte 3/4 idiom copied into Svelte 5 project or vice versa. Detect version/source first.

- SSR crash: module top-level reads `window`/localStorage. Move to browser boundary.

- Hydration mismatch: server and client render nondeterministic values. Stabilize initial render.

- Effect-derived state loop: synchronization used instead of derivation. Use derived state.

- Route data duplicate fetch: component bypasses SvelteKit data lifecycle. Use canonical route architecture.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run Svelte/SvelteKit check, lint and build under project config.

- Test SSR render plus browser hydration for changed route/components.

- Exercise form/load error and invalidation behavior.

- Test browser-only lifecycle cleanup and navigation between routes.

- Inspect generated/client bundle when introducing large browser dependencies.

- Run the project's canonical Svelte formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Svelte version and architecture.

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
