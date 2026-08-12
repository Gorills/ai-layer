---
slug: fastapi
description: FastAPI engineering for dependency boundaries, validation schemas, async I/O, lifespan, errors, OpenAPI and production-safe request handling.
kind: stack
keywords:
- fastapi
- pydantic
- starlette
- dependency injection
- async
- lifespan
- openapi
- router
- background tasks
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# FastAPI Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring FastAPI code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual FastAPI version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established FastAPI architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Keep route handlers thin: validate/authorize/translate, call an application use case, then map output/errors to HTTP.

- Treat dependency injection as request/composition infrastructure, not a hidden service locator for business logic.

- Use explicit response models/status/error schemas where API contract matters; framework-generated OpenAPI is only as accurate as the declared behavior.

- Match sync versus async handlers/dependencies to underlying I/O. Blocking database/SDK/filesystem calls inside async functions can stall the event loop.

- Use lifespan for application-owned long-lived clients/resources and close them deterministically; avoid import-time client/session creation.

- Do not rely on `BackgroundTasks` for durable business work that must survive process restart; use a durable queue/outbox when reliability matters.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the FastAPI and toolchain versions.

- FastAPI, Starlette, Pydantic and Python versions from lockfile because compatible APIs/config changed across major versions.

- Application/router composition, dependencies, lifespan handlers and middleware order.

- Pydantic request/response models, exception handlers and sync/async database/client boundaries.

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

- If a dependency contains business branching or writes, move it into the use case and keep dependency focused on context/resource acquisition.

- If a route is `async def` but calls sync blocking SDK/ORM, switch to correct sync execution/offload/async client rather than assuming FastAPI handles arbitrary blocking code.

- If work must complete even after worker crash/deploy, enqueue durable work; in-process background task is insufficient.

- If response schema intentionally differs from internal/domain object, map explicitly rather than returning ORM/vendor objects directly.

## Workflow

1. Detect FastAPI version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Group routers by capability and compose dependencies at router/endpoint scope where ownership is visible.

- Use Pydantic models for transport validation; separate domain/application types when transport optionality/aliases differ.

- Use exception handlers to map stable application errors, keeping traceback/internal exceptions out of public responses.

- Create one configured outbound client/database pool in lifespan and inject/adapt it rather than constructing per request.

- Use dependency overrides in tests only at intended boundaries and keep integration tests for actual routing/serialization.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Dependency business logic: authorization/mutation hidden in nested Depends graph makes flow opaque. Keep use case explicit.

- Async blocking: sync I/O in async route stalls server. Use correct execution model.

- Import-time resource: event loop/client lifecycle differs under workers/tests. Own it in lifespan.

- BackgroundTasks durability assumption: deploy loses critical work. Use durable worker.

- Pydantic/version confusion: examples from v1/v2 or FastAPI releases mixed. Detect versions/source first.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run FastAPI app startup/lifespan tests and ensure resources close on failure/shutdown.

- Use test client/ASGI client to verify real status, serialization, validation and exception mapping.

- Test sync/async timeout/cancellation behavior for changed external/database calls.

- Inspect generated OpenAPI diff for accidental contract change.

- Load/profiling check for request paths that add blocking or per-request expensive initialization.

- Run the project's canonical FastAPI formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual FastAPI version and architecture.

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
