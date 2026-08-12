---
slug: html
description: Semantic HTML engineering for document structure, native controls, forms, metadata, links, media and accessible browser behavior.
kind: stack
keywords:
- html
- semantic html
- forms
- button
- link
- heading
- landmark
- metadata
- native controls
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# HTML Semantics Skill

## Apply when

Use when implementing, reviewing or refactoring HTML code in a project that actually uses this stack. Detect the project version, configuration and established architecture first; combine this skill with domain skills such as backend, frontend, database, security or testing rather than treating framework syntax as the whole design.

## Core contract

- Detect the actual HTML version and project configuration from manifests/lockfiles/runtime evidence before relying on version-sensitive APIs or defaults.

- Follow the repository's established HTML architecture, naming, dependency boundaries and tooling unless the task explicitly changes them.

- Keep business/domain decisions outside framework glue where the existing architecture has such a boundary; framework convenience should not create a second business flow.

- Use the framework/language's native, maintained primitives before adding custom abstractions or dependencies; verify uncertain behavior in official version-matched documentation.

- Make error, async/concurrency, resource lifecycle and cancellation behavior explicit where the stack exposes them; happy-path syntax is not enough.

- Preserve typing/schema/validation strength rather than escaping it with broad dynamic types, unchecked casts or generic dictionaries to make code compile.

- Respect package/dependency boundaries and lockfile discipline; adding or upgrading dependencies needs a concrete capability, compatibility and security reason.

- Keep hot paths bounded and measure performance before stack-specific micro-optimization; understand when the runtime/framework performs implicit I/O or repeated work.

- Use the project's canonical formatter, linter, type/static checks and test runner; stack-specific correctness must survive the full repository gate.

- Use elements for their semantic role: buttons perform actions, anchors navigate, headings structure content, lists group lists and tables represent tabular data.

- Maintain a logical heading/document outline and landmark structure without choosing heading levels for visual size.

- Form controls need persistent labels, appropriate input types/autocomplete and server-side validation regardless of client constraints.

- Interactive content nesting must remain valid and predictable; do not put buttons/links inside conflicting interactive containers.

- Document metadata should describe real page semantics and avoid duplicate/conflicting canonical/index directives.

## Evidence to inspect

- Manifest/lockfile and runtime output proving the HTML and toolchain versions.

- Rendered DOM and template/component source that generates markup.

- Heading/landmark hierarchy, form label/control relationships and link/button usage.

- Document metadata, language, viewport and media semantics.

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

- If clicking changes URL/location/history to another resource, use a real link; if it performs an action in-place, use a button.

- If a native form/input element supports the interaction, prefer it before recreating with ARIA/custom JS.

- If layout requires a table-like appearance but data is not tabular, use CSS layout; if data is comparable rows/columns, preserve table semantics.

## Workflow

1. Detect HTML version, project layout, config, package manager and canonical commands.

2. Trace the existing feature path and identify framework entry points versus application/domain ownership.

3. Confirm any version-sensitive API in authoritative docs or an executable minimal reproduction.

4. Implement through existing project abstractions with strong types/validation and bounded side effects.

5. Handle relevant errors, cancellation/retry/resource cleanup and security constraints explicitly.

6. Add focused tests using the stack's real runtime/framework boundary where semantics depend on it.

7. Run formatter/linter/type/static checks plus targeted tests, then the repository's canonical quality gate.

8. Inspect final diff for dependency/config churn, duplicate patterns and behavior hidden in framework callbacks.

## Implementation patterns

- Use `main`, `nav`, `header`, `footer`, `aside` landmarks where they reflect actual page regions without creating redundant landmark noise.

- Associate labels using explicit `for`/id or wrapping as appropriate; use `fieldset`/`legend` for grouped choices.

- Use responsive images (`srcset`/`sizes`/picture) when asset variants exist and layout benefits.

- Use loading/lazy attributes deliberately; do not lazy-load critical above-the-fold assets blindly.

- Keep DOM order aligned with reading/focus order and use CSS for visual layout.

- Keep adapters at external boundaries so stack/library-specific types do not become the public model of unrelated modules.

- Prefer explicit dependency construction/composition over hidden globals/service locators when the project architecture supports injection.

- Centralize shared configuration and lifecycle setup; do not repeat slightly different clients/middleware/runtime settings per feature.

- Use small named helpers for non-obvious protocol/runtime rules and cover them with focused tests rather than dense inline cleverness.

## Failure modes

- Clickable div loses keyboard/semantics. Replace with button/link.

- Heading by font size produces skipped/random outline. Choose semantic level then style.

- Placeholder as label disappears and harms forms. Add persistent label.

- Nested interactive controls create invalid/focus behavior. Restructure hit targets.

- DOM order differs drastically from visual CSS order. Fix structural order.

- Version-memory bug: code uses an API/default from another major/minor. Detect version and source-first verify.

- Framework leakage: core business rules become coupled to request/ORM/component/runtime objects. Translate at boundary where architecture requires it.

- Type escape spread: one `any`/unchecked cast/dynamic dictionary propagates and removes useful guarantees. Narrow the unsafe boundary.

- Dependency reflex: new package is added for trivial behavior, increasing supply-chain and upgrade cost. Prefer native capabilities when sufficient.

- Local green only: one stack-specific test passes but formatter/type/package/full gates fail. Run canonical quality.

## Verification

- Validate rendered DOM for duplicate IDs/invalid nesting when tooling supports it.

- Keyboard through native controls and verify form submission/labels/errors.

- Inspect accessibility tree/landmarks/headings on representative page.

- Verify metadata/canonical/robots directives in actual server-rendered output where SEO matters.

- Run the project's canonical HTML formatter/linter/static or type checks.

- Run focused tests for changed behavior plus boundary/failure cases.

- Run the repository's aggregate quality gate from the final source state.

- Check dependency/lock/config diffs for accidental broad changes.

- Verify any version-sensitive claim against detected version and authoritative docs.

## Completion criteria

- The implementation is idiomatic for the project's actual HTML version and architecture.

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
