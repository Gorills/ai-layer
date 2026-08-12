---
slug: javascript
description: JavaScript engineering for module boundaries, async control flow, runtime types, errors, browser or Node semantics and dependency-safe code.
kind: stack
keywords:
- javascript
- esm
- promise
- async
- event loop
- modules
- errors
- runtime validation
- npm
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# JavaScript Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring JavaScript code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual JavaScript version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established JavaScript architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Treat asynchronous errors explicitly: await/return promises, handle rejection at ownership boundaries and avoid floating promises.

- Use strict equality and explicit coercion/parsing at boundaries; JavaScript coercion should not silently define business rules.

- Prefer immutable/local data transformations and clear object ownership over mutation shared across callbacks.

- Use modern module syntax consistent with project/runtime and avoid mixing CJS/ESM hacks without compatibility evidence.

- Validate external JSON because TypeScript annotations or JSDoc do not exist at runtime.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the JavaScript and toolchain versions.

- `package.json`/lockfile, module type (ESM/CJS), runtime/browser targets and transpilation/bundler configuration.

- Promise/async chains, event listeners/timers and cancellation/AbortSignal usage.

- Runtime validation at API/storage/message boundaries and lint rules.

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

- If an async operation can become obsolete, use AbortSignal/request identity or state checks to prevent stale completion effects.

- If object property absence differs from `undefined`/`null`, define the contract before using truthiness.

- If a function accepts multiple loosely typed shapes, normalize once at boundary rather than accumulating branching internals.

## Workflow

1. Detect JavaScript version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use `AbortController` for cancellable fetch/async APIs that support it and propagate signal through adapters.

- Use `URL`/`URLSearchParams` rather than string concatenation for URLs/query encoding.

- Use `Map`/`Set` when key identity or membership semantics are clearer than object/array scans.

- Use optional chaining/nullish coalescing intentionally; do not let them hide required-data violations.

- Keep side-effectful module initialization minimal so tests/build/runtime loading remain predictable.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Floating promise causes unhandled rejection or work finishing after lifecycle; await/return/own it.

- Truthiness bug treats `0`, `false` or empty string as absent. Use explicit null/undefined/domain checks.

- JSON trust: remote payload assumed to match expected shape. Validate before use.

- Listener/timer leak: component/request lifecycle ends but callback remains. Remove/cancel on cleanup.

- ESM/CJS mismatch works locally through transpiler but fails in production runtime. Match actual target.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run configured ESLint/formatter and test runtime under target module system.

- Test rejected promises, cancellation and stale-response behavior for async changes.

- Test external payload validation with missing/null/wrong-type values.

- Inspect build/runtime output for module-resolution or bundle regressions when dependencies/import style changes.

- Run the project's canonical JavaScript formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual JavaScript version and architecture.

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
