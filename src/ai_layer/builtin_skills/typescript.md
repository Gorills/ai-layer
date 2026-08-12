---
slug: typescript
description: TypeScript engineering for strict domain models, narrowing, generics, runtime validation, module APIs and sound boundary design.
kind: stack
keywords:
- typescript
- types
- strict
- generics
- narrowing
- discriminated union
- unknown
- tsconfig
- runtime validation
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# TypeScript Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring TypeScript code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual TypeScript version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established TypeScript architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use `unknown` for untrusted values and narrow/validate before use; `any` disables the safety the skill is meant to provide.

- Model mutually exclusive states as discriminated unions instead of bags of optional fields that allow impossible combinations.

- Avoid non-null assertions/type assertions unless an external invariant is proven at runtime or structurally and the assertion boundary is narrow.

- Make public generic constraints express actual requirements; clever conditional types are a maintenance cost when a simpler model works.

- Remember types erase at runtime: external payloads, environment/config and persisted data need runtime validation.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the TypeScript and toolchain versions.

- `tsconfig` strictness/options, project references, generated types and supported runtime targets.

- Public type exports, discriminated unions, generic helpers and places using `any`, assertions or `@ts-ignore`.

- Runtime validators/schemas at network/storage/message boundaries.

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

- If a state machine has several booleans/optional properties, prefer a discriminated union that makes invalid combinations unrepresentable.

- If a cast is needed after parsing JSON, replace it with schema/guard validation rather than asserting desired shape.

- If generics make call sites harder to understand than duplicated concrete types, simplify; abstraction should improve correctness/readability.

## Workflow

1. Detect TypeScript version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use exhaustive `switch` with `never`/project pattern to make new union variants compile-time visible.

- Use branded/opaque types sparingly for identifiers/units that are easy to mix and high-cost when mixed.

- Use `satisfies` where it preserves inference while checking structural conformance, subject to pinned version.

- Keep DTO/API schema types separate from richer internal/domain types when nullability/semantics differ.

- Generate types from canonical schemas only when generation is deterministic and part of quality/release flow.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- `as Foo` after JSON turns wish into type. Validate at runtime.

- Optional-field soup permits impossible loading/error/data combinations. Use unions.

- Global `any` escape spreads unsafe operations. Constrain unknown boundary.

- Deep conditional type wizardry slows compiler and maintainers for little value. Prefer explicit types.

- Frontend/backend generated type drift because artifact is stale. Make generation/check deterministic.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Run `tsc --noEmit` or configured type-check command under the project tsconfig.

- Search changed code for new `any`, non-null assertions, `@ts-ignore`/unchecked casts and justify/remove them.

- Test runtime validators with malformed/missing/null/extra fields.

- Compile/build generated type artifacts and verify no stale diff when the project uses codegen.

- Run the project's canonical TypeScript formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual TypeScript version and architecture.

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
