---
slug: css
description: CSS engineering for cascade, layout, responsive systems, tokens, containment, state styling and maintainable visual implementation.
kind: stack
keywords:
- css
- cascade
- grid
- flexbox
- responsive
- container query
- specificity
- tokens
- layout
- styles
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# CSS Engineering Skill

## Apply when

Use when implementing, reviewing or refactoring CSS code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual CSS version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established CSS architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use the cascade intentionally: keep specificity low/predictable and fix ownership rather than escalating with selectors or `!important`.

- Choose Grid for two-dimensional/shared track alignment and Flexbox for one-dimensional distribution; avoid absolute positioning for normal flow.

- Use design tokens/custom properties for repeated semantic values while avoiding a token for every one-off pixel.

- Prefer intrinsic/responsive sizing (`minmax`, `clamp`, flex/grid constraints) over viewport-specific hardcoded widths when content should adapt.

- Understand containing blocks, stacking contexts and overflow before adding arbitrary `z-index` values.

- Keep component state styling tied to semantic classes/attributes/pseudo-classes and preserve focus-visible/accessibility.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the CSS and toolchain versions.

- Global/reset/theme/token layers and component stylesheet strategy (modules, scoped CSS, utility classes, CSS-in-JS, etc.).

- Computed styles/specificity and actual layout boxes for affected elements.

- Responsive breakpoints/container logic, overflow/scroll ownership and stacking contexts.

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

- If layout requires repeated negative margins/absolute offsets, revisit parent layout/grid before patching children.

- If an override needs higher specificity than the whole component system, locate incorrect source/cascade layer rather than starting a specificity arms race.

- If viewport breakpoints depend on component width, use container-query architecture when supported by the project's target browsers and design.

## Workflow

1. Detect CSS version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use `box-sizing: border-box` in the established reset and reason from final box dimensions.

- Use logical properties when writing-mode/localization support matters and project conventions permit.

- Use `min-width: 0`/overflow rules intentionally for flex/grid children with long content instead of global `overflow:hidden`.

- Define focus/hover/disabled/selected states alongside base component CSS, not in unrelated page overrides.

- Prefer shared spacing/type/color tokens but keep component-specific geometry close to component ownership.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Specificity war: IDs/deep nesting/`!important` accumulate. Reset ownership and lower selectors.

- Absolute-layout UI breaks long content/responsive. Use flow/grid/flex.

- Global overflow hidden hides underlying layout defects and keyboard content. Fix source.

- Z-index inflation fails because elements are in different stacking contexts. Inspect context roots.

- Magic breakpoints proliferate per component without content reason. Consolidate around layout transitions.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Inspect computed styles for unintended override/specificity and browser console for invalid CSS.

- Render at relevant widths/heights with long content and focus/selected/error states.

- Check horizontal overflow, scroll containers and sticky/fixed elements.

- Run configured CSS/style lint/build and visual QA rather than source-only review.

- Run the project's canonical CSS formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual CSS version and architecture.

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
