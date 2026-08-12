---
slug: laravel
description: Laravel engineering for Eloquent queries, service boundaries, queues, validation, authorization, transactions, migrations and production lifecycle.
kind: stack
keywords:
- laravel
- eloquent
- artisan
- migration
- queue
- job
- policy
- validation
- service container
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Laravel Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring Laravel code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Laravel version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Laravel architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Keep controllers, console commands and jobs as transports/orchestrators into one application behavior rather than duplicating business rules.

- Eloquent convenience does not remove SQL costs: prevent N+1, bound collections and inspect eager loading/query plans.

- Use Form Request/validator at transport boundary and Policies/Gates for authorization, while keeping durable domain invariants below transport.

- Use DB transactions around local mutations and avoid slow external network calls while locks are held.

- Queued jobs must be idempotent/retry-safe and use explicit timeout/backoff/failure behavior; serialization means model/data may change before execution.

- Treat model observers/events as implicit global coupling; use them only where ordering/transaction/retry semantics are understood.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Laravel and toolchain versions.

- Laravel/PHP version, Composer lock, providers/container bindings, route/middleware registration.

- Eloquent models/scopes/relationships, migrations and query behavior.

- Jobs/queues/events/listeners, retry/timeout/uniqueness and transaction interaction.

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

- If a model event triggers external side effect before commit, move it to after-commit/durable outbox/job semantics appropriate to reliability need.

- If a job receives an Eloquent model object and semantics depend on snapshot state, pass stable identifiers/version/snapshot deliberately and re-authorize/reload as needed.

- If a relationship is accessed per item in resource/serializer loop, eager load the exact graph and test query count.

## Workflow

1. Detect Laravel version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use Policies for resource/action authorization and keep controller checks delegated to them.

- Use custom query scopes for reusable filtering/tenant constraints while preserving clear unscoped admin escape policy.

- Use queued jobs for durable asynchronous work with unique/idempotency keys and retry classification.

- Use API Resources/DTOs to keep public contract separate from Eloquent internals.

- Use service container bindings at composition boundaries; avoid resolving arbitrary dependencies globally inside domain code.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Fat Eloquent model/observer: hidden workflows fire in seed/import/admin/tests. Move explicit use-case logic.

- N+1 Resource: serialization triggers relationship queries. Eager-load/measure.

- Job retry duplication: each attempt repeats irreversible effect. Add idempotency/durable operation state.

- Migration generated then run blindly on huge table. Plan expand/backfill/contract and locking.

- Facade/service-locator spread: dependencies become invisible and hard to test. Inject owned collaborators.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run Laravel/PHP canonical tests, static analysis and formatter.

- Use database integration tests for transactions/constraints and query-count inspection for hot lists.

- Test queued job duplicate/retry/failure lifecycle and after-commit expectations.

- Run migration upgrade on representative old data and verify rollback/mixed-version plan.

- Test Policies/Gates through actual route plus direct policy matrix.

- Run the project's canonical Laravel formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Laravel version and architecture.

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
