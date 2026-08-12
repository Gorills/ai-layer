---
slug: python
description: Python engineering for typing, exceptions, resource management, concurrency, packaging, data models and maintainable runtime behavior.
kind: stack
keywords:
- python
- typing
- asyncio
- dataclass
- exception
- context manager
- packaging
- pytest
- ruff
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Python Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring Python code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Python version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Python architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use context managers/finally for files, locks, DB sessions and temporary resources; deterministic cleanup is part of correctness.

- Use specific exceptions with stable ownership; avoid broad `except Exception` unless translating/logging at a true boundary and re-raising or handling deliberately.

- Do not call blocking I/O inside an async event loop without an explicit thread/process/offload strategy.

- Keep mutable defaults out of function/dataclass definitions and make object ownership/copying semantics clear.

- Favor explicit typed models/protocols over nested untyped dicts when data crosses module boundaries.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Python and toolchain versions.

- `pyproject.toml`/lock data, supported Python versions, type checker/linter settings and package layout.

- Sync/async boundaries, thread/process usage, context managers and resource-owning code.

- Data models/dataclasses/Pydantic or equivalent validation boundaries and exception taxonomy.

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

- If a function can be synchronous and is called in sync paths, do not make it async merely because surrounding framework supports async.

- If CPU-heavy work runs in async server code, use process/offload/job architecture rather than assuming `async` makes CPU work concurrent.

- If runtime import cycles appear, fix module ownership; `TYPE_CHECKING` can solve type-only cycles but should not hide architectural cycles.

## Workflow

1. Detect Python version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use `pathlib.Path` for filesystem path semantics and explicit encodings for text I/O.

- Use `dataclass`/typed models for owned structured data and Protocol/ABC only where polymorphic boundary value exists.

- For asyncio, propagate cancellation, bound task lifetime and use task groups/structured concurrency primitives available to the pinned version.

- Use iterators/generators/streaming for large sequences when the consumer does not need full materialization.

- Use timezone-aware datetimes for durable/external time and normalize at boundaries.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Concurrency and async

- Async is a concurrency model for waiting on I/O, not an automatic performance mode. Keep blocking calls off the event loop and make cancellation paths cleanup-safe.

- Do not orphan background tasks created with bare `create_task`; retain ownership, handle exceptions and define shutdown semantics.

- Thread safety still matters for mutable shared objects accessed from worker threads; the GIL is not a substitute for application invariants.

- Multiprocessing changes serialization, startup and resource ownership; test worker initialization/shutdown rather than assuming fork behavior.

## Failure modes

- Bare/broad exception swallowing hides cancellation/programming errors; catch only errors you can handle and preserve cause/context.

- Async function calls blocking SDK/filesystem/CPU and stalls all requests; offload or use async-capable dependency.

- Mutable default/list/class state leaks between calls/tests; create per-instance/per-call state.

- Import-time side effects make tests/workers/startup unpredictable; move initialization to composition/lifecycle.

- Untyped dictionary plumbing causes key/shape errors far from boundary; validate/normalize once.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run configured Ruff/format, mypy or the project's type checker on changed modules.

- Exercise async cancellation/timeouts and resource cleanup if async/lifecycle code changed.

- Test exception mapping and `__cause__`/diagnostic preservation at boundaries.

- Run on the project's minimum supported Python version when compatibility is material.

- Run the project's canonical Python formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Python version and architecture.

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
