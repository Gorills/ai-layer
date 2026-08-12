---
slug: php
description: PHP engineering for strict types, value objects, exceptions, dependency boundaries, Composer, request isolation and reliable runtime behavior.
kind: stack
keywords:
- php
- composer
- strict_types
- psr
- exceptions
- value object
- phpstan
- psalm
- autoload
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# PHP Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring PHP code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual PHP version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established PHP architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use `declare(strict_types=1)` according to project convention and model nullability/union types explicitly rather than relying on coercion.

- Prefer typed DTOs/value objects for domain/boundary data over associative arrays with undocumented keys.

- Throw/catch specific exceptions at ownership boundaries; do not convert all failures to `false`/null or broad generic exceptions.

- Respect PHP request versus long-running worker lifecycle: static/singleton mutable state that is harmless under FPM can leak across jobs in persistent workers.

- Use Composer autoloading/package constraints and lockfile discipline; do not manually include vendor files or broaden constraints casually.

- Use maintained password/crypto/escaping/database APIs rather than custom primitives.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the PHP and toolchain versions.

- PHP version/platform requirements, Composer lockfile/autoload and static-analysis level.

- Framework/container boundaries, request lifecycle and long-running worker behavior if applicable.

- DTO/value objects, nullability, exception hierarchy and filesystem/network/database resource code.

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

- If an associative array crosses several layers with required keys, introduce a typed DTO/value object or validated schema.

- If API returns nullable/false/exception alternatives, normalize once into an explicit result/error contract.

- If code runs under queue/RoadRunner/Swoole-like long-lived process, audit mutable globals/static caches and connection lifecycle.

## Workflow

1. Detect PHP version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use readonly/value objects where supported by pinned PHP and beneficial for invariant-rich immutable data.

- Use interfaces at true external/substitution boundaries, not for every service solely to satisfy container convention.

- Use constructor injection and one composition/container registration path for required dependencies.

- Use generators/streams for large data exports/imports rather than concatenating entire content.

- Use static analysis annotations/generics only to strengthen real contracts and keep them synchronized with native types.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Array-shape sprawl: misspelled keys fail at runtime far away. Use typed/validated structures.

- False/null/error ambiguity: callers forget one sentinel. Normalize explicit result/exception.

- Static state leak in worker: one job/tenant affects next. Reset/remove request-local statics.

- Composer constraint drift: unbounded update changes many packages. Keep lock diff intentional.

- Catch Throwable everywhere and continue: programming errors hidden. Catch only recoverable boundary errors.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run configured PHPStan/Psalm at project level plus formatter/linter.

- Run tests under supported minimum/current PHP runtime as compatibility requires.

- Test long-running worker repeated jobs if runtime persists process state.

- Inspect Composer lock diff and `composer validate`/project equivalent.

- Test exception/nullable boundary cases and large-stream resource cleanup.

- Run the project's canonical PHP formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual PHP version and architecture.

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
