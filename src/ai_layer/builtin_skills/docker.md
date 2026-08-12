---
slug: docker
description: Docker engineering for reproducible builds, minimal runtime images, cache strategy, non-root execution, secrets and reliable container lifecycle.
kind: stack
keywords:
- docker
- dockerfile
- container
- image
- buildkit
- multi-stage
- compose
- non-root
- healthcheck
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Docker and Container Skill

## Apply when

Use when implementing, reviewing or refactoring Docker code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual Docker version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established Docker architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use multi-stage builds to separate build tooling from runtime artifacts when the stack benefits; final image should contain only runtime necessities.

- Pin base images/dependencies according to project reproducibility/security policy and update intentionally; floating tags make builds nonreproducible.

- Order Dockerfile layers to maximize stable dependency cache without hiding stale/generated artifact problems.

- Run as non-root in final image unless a concrete runtime need requires privilege, and set file ownership explicitly.

- Do not bake secrets into ARG/ENV/layers or copy broad home/config directories into images.

- Use exec-form entrypoint/CMD and ensure application receives termination signals and shuts down gracefully.

- Keep build context small with `.dockerignore`; copy explicit files/stages rather than repository-wide junk.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the Docker and toolchain versions.

- Dockerfile stages/base image pins, `.dockerignore`, build context and Compose/deployment manifests.

- Runtime user/filesystem permissions, entrypoint/CMD, exposed ports and signal handling.

- Build secrets/args/environment, copied artifacts and image layer contents.

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

- If build requires credentials, use BuildKit secret/SSH mounts or CI-native secret mechanism that does not persist in layers.

- If a package manager supports locked/reproducible install, use the lockfile-specific frozen command before copying frequently changing source.

- If one image includes compilers/package caches/dev dependencies at runtime, split build/runtime stages unless runtime genuinely needs them.

## Workflow

1. Detect Docker version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Copy lock/manifests first, install dependencies, then source where this preserves cache and does not break workspace semantics.

- Create a dedicated runtime user and chown only required writable paths.

- Use health checks/readiness at orchestration layer according to actual application semantics; do not make liveness depend on optional external services.

- Use immutable image artifacts and external runtime configuration rather than mutating code inside running containers.

- Clean package-manager caches in the same layer or use cache mounts where appropriate.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Build and runtime boundaries

- A Docker build should produce the deployable artifact; do not depend on bind-mounted source or host-installed dependencies for production behavior.

- Separate build-time values from runtime configuration. Values needed only to compile may be build args, but secrets and environment-specific credentials belong outside the image.

- Final stages should copy named artifacts from build stages, making it obvious what crosses the trust/size boundary.

- Treat base-image updates as dependency upgrades with tests, not automatic unreviewed drift.

## Failure modes

- Secret layer leak: secret deleted later but remains in history. Use secret mounts, never COPY/ARG for secret material.

- Root runtime: compromise gains unnecessary container privilege. Use dedicated user.

- Signal shell wrapper: app does not receive SIGTERM and is killed hard. Exec/forward signals.

- Huge context/image: `.git`, tests, caches and build toolchain copied. Tighten ignore/stages.

- Floating base: rebuild changes unexpectedly. Pin/update via deliberate process.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Build image with BuildKit and inspect final stage size/layers/content for unexpected tools/secrets.

- Run container as configured user and verify only intended paths are writable.

- Send SIGTERM during active work and verify graceful exit within platform deadline.

- Run vulnerability/image scanning configured by project and triage base/dependency findings.

- Build twice from same source under deterministic policy where repository enforces reproducibility.

- Run the project's canonical Docker formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual Docker version and architecture.

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
