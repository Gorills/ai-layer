---
slug: django
description: Django engineering for models, ORM queries, transactions, migrations, request boundaries, async constraints, security and production-safe application structure.
kind: stack
keywords:
- django
- django orm
- django migration
- model
- queryset
- transaction
- middleware
- admin
- async django
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Django Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring Django code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Django version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Django architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Keep business rules out of views/admin/model `save()` hooks when they form multi-step use cases; use the project's canonical service/application layer so CLI/jobs/API share behavior.

- Use ORM querysets intentionally: know when evaluation occurs, avoid accidental repeated queries and solve N+1 with `select_related`/`prefetch_related` based on relation shape.

- Use `transaction.atomic` around the actual durable unit of work, not broad request/network spans; use database constraints for durable invariants.

- Treat model signals as global implicit hooks: use them only when hidden coupling is acceptable and ordering/transaction behavior is understood.

- Respect Django's async/sync boundary; do not call sync-only ORM/blocking work directly from async contexts without supported bridging.

- Use framework security defaults for CSRF, sessions, escaping, host validation and password handling rather than disabling them to simplify integration.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Django and toolchain versions.

- Django/Python version, settings split, installed apps, middleware and URL/ASGI/WSGI entry points.

- Models/managers/querysets, migrations, transaction usage and query count on affected paths.

- Views/DRF or other transport layer, forms/serializers and permission boundaries.

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

- If logic must run from API, management command and worker, put it in one application/service function rather than a view/model-signal copy.

- If a queryset is accessed inside a loop for related objects, inspect generated query count and eager-load the right relation.

- If side effects should happen only after a successful DB commit, use `transaction.on_commit` or a durable outbox rather than performing irreversible work inside an uncommitted transaction.

- If changing a model field in deployed system, inspect historical migrations and plan compatibility/backfill before changing code assumptions.

## Workflow

1. Detect Django version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use custom QuerySet/Manager for reusable query semantics/scopes, not as a dumping ground for orchestration side effects.

- Use `select_related` for appropriate single-valued joins and `prefetch_related` for multi-valued/reverse relations; verify rather than cargo-culting both.

- Use model/database constraints (`UniqueConstraint`, `CheckConstraint`, FK semantics) for invariants that must hold across writers.

- Use forms/serializers/request schemas for boundary validation and normalize to application inputs.

- Use management commands as thin operational transports into reusable application logic with clear exit/error behavior.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Migrations

- Never rewrite historical migrations that may have been applied in shared/deployed environments merely to clean the graph; add a new migration unless an explicitly coordinated squash policy applies.

- For required fields on existing tables, use an expand/backfill/enforce sequence instead of assuming a one-shot generated migration is safe.

- Data migrations should use historical models from the migration app registry rather than importing current models whose schema/behavior may differ.

- Large backfills should be restartable and bounded; a migration transaction that updates millions of rows can be operationally unsafe.

- Review generated operations for locks, defaults, index construction and mixed-version compatibility. `makemigrations` produces syntax, not a deployment plan.

- When a field/table is being replaced, make old and new code/data coexist through the required rollout window before removing the historical representation.

## Failure modes

- Fat model/save signal: hidden side effects trigger on fixtures/admin/imports unexpectedly. Move use-case orchestration to explicit service.

- N+1 queryset: template/serializer triggers per-row related query. Measure and eager-load.

- Historical migration edit: fresh install works but deployed migration graph diverges. Append migration; don't rewrite applied history.

- Network call in atomic block: locks remain during provider latency. Record intent/commit then call asynchronously or after commit.

- Async view with sync ORM misuse: event loop blocks or Django raises safety errors. Use supported async ORM/bridging for pinned version.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run `manage.py check` and project-specific deployment/system checks where configured.

- Run migration graph/check commands and tests against the supported database, not an in-memory substitute for DB-specific behavior.

- Use query-count assertions/profiling for changed list/serializer/template paths vulnerable to N+1.

- Test transaction rollback and `on_commit` behavior for side-effectful flows.

- Test CSRF/session/permission behavior through real request client for security-sensitive views.

- Run the project's canonical Django formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Django version and architecture.

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
