---
slug: node
description: Node.js backend runtime discipline for event-loop safety, streams, process lifecycle, modules, errors, HTTP clients and resource cleanup.
kind: stack
keywords:
- node
- nodejs
- event loop
- stream
- buffer
- esm
- process
- worker thread
- http
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Node.js Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring Node.js code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Node.js version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Node.js architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Do not block the event loop with CPU-heavy synchronous work or synchronous filesystem/crypto operations in request paths.

- Use streams with backpressure for large data rather than buffering entire files/responses into memory.

- Own process lifecycle explicitly: startup failure, SIGTERM/shutdown, draining servers/queues and closing pools/clients.

- Keep ESM/CommonJS usage consistent with runtime/package configuration and dependency exports.

- Treat uncaught exceptions/unhandled rejections as correctness signals; do not install handlers that merely log and continue in potentially corrupted state.

- Bound outbound HTTP operations with timeouts/cancellation and safely consume/close response bodies according to chosen client.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Node.js and toolchain versions.

- Node engine version, module mode, package manager/lockfile and process/container entrypoint.

- Event-loop blocking operations, streams/backpressure, timers and worker/thread usage.

- Process signals, startup/shutdown hooks, connection pools and unhandled rejection/exception policy.

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

- If CPU work is material, use worker threads/process/job architecture based on latency/isolation needs rather than promise/async syntax.

- If stream producer can outpace consumer, use pipeline/backpressure rather than manual `data` concatenation.

- If graceful shutdown matters, stop accepting new work, drain bounded in-flight operations and close durable resources before deadline.

## Workflow

1. Detect Node.js version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use `stream.pipeline`/promise equivalents for propagation and cleanup of multi-stage streams.

- Use `AbortSignal` for cancellation/timeout through supported Node APIs.

- Centralize configured HTTP/DB clients and close them in application lifecycle.

- Use worker threads for CPU-bound JS when appropriate; processes/jobs may provide stronger fault/memory isolation.

- Validate environment/config at startup and fail clearly before serving traffic.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Sync CPU/I/O in request handler stalls all connections. Offload/use async.

- Buffer-all upload/download exhausts memory. Stream with limits/backpressure.

- Signal ignored: container kills process mid-transaction/job. Implement graceful bounded shutdown.

- Unhandled rejection swallowed by global listener and process continues unpredictably. Fix ownership/error policy.

- ESM/CJS interop hack breaks on runtime upgrade. Match package exports/module mode.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run under the project's declared minimum/production Node version.

- Load-test or instrument event-loop delay for changes that add CPU/large I/O hot paths.

- Test graceful SIGTERM with in-flight request/job and verify pool/client cleanup.

- Test stream error/abort and ensure file/network handles close.

- Run build/module-resolution tests in production entrypoint mode.

- Run the project's canonical Node.js formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Node.js version and architecture.

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
