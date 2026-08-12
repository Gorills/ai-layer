---
slug: frontend
description: Frontend engineering for component boundaries, state ownership, data fetching, accessibility, performance, resilience and maintainable user interactions.
kind: domain
keywords:
- frontend
- ui
- component
- state
- data fetching
- routing
- forms
- browser
- client
- rendering
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Frontend Engineering Skill

## Apply when

Use for browser-side application features, component architecture, state/data flows, forms, navigation, client caching and UI behavior. Combine with `design` for visual decisions and the specific framework skill for idiomatic implementation.

## Core contract

- Model user state and server state separately. Do not duplicate the same fact in several local/global/cache stores without a clear authority.

- Components should own presentation/local interaction state; business/server mutations should flow through explicit services/hooks/stores consistent with the project.

- Keep derived state derived. Storing filtered/sorted/combined copies creates synchronization bugs unless there is a measured reason.

- Handle the full async lifecycle: initial, loading/reloading, success, empty, validation error, network/server error and stale/optimistic state.

- Accessibility and keyboard behavior belong in component design, not a final wrapper pass.

- Preserve browser/navigation semantics: URLs, back/forward, links, focus, scroll restoration and form behavior where applicable.

- Avoid broad rerenders and huge client bundles by measuring component/data boundaries before premature micro-optimization.

- Treat HTML from users/servers as untrusted; do not bypass framework escaping without sanitization and a documented need.

- Data fetching must define cancellation/stale-response/race behavior when route/filter/input changes can overlap requests.

- Visual correctness requires rendered inspection with realistic content and responsive states.

## Evidence to inspect

- Component tree, routing, state stores/context, query/cache library and API client.

- Existing design system/component primitives and accessibility conventions.

- Server API contracts and cache invalidation/update semantics after mutations.

- Bundle/chunk boundaries and browser performance traces for performance-sensitive work.

- Forms/validation/error handling and URL/query state.

- Existing component/integration/E2E tests plus screenshots/visual QA tooling.

## Decision rules

- If state can be computed from props/server data/other state, compute it rather than syncing a duplicate state variable.

- If state is used by one component subtree, keep it local before promoting to global storage.

- If several screens share server data, use the established query/cache layer and define invalidation/update after mutations.

- If fast successive requests can complete out of order, cancel obsolete requests or bind results to the request identity/version.

- If a UI behavior should survive refresh/share/back navigation, consider URL/server persistence rather than ephemeral component state.

- If a component accumulates unrelated data fetching, orchestration and presentation branches, split by responsibility/user concept rather than arbitrary line count.

- If rendering user-provided rich text is required, use a vetted sanitization/rendering path; never generic unsafe HTML injection.

- If a list can be large, use server pagination/windowing/virtualization only after preserving accessibility and interaction semantics.

## Workflow

1. Trace the user journey and authoritative data sources, including URL/server/client state.

2. Identify component boundaries based on reusable behavior and change ownership, not simply visual boxes.

3. Define loading/empty/error/optimistic states and mutation/cache behavior before happy-path markup is finished.

4. Implement semantic structure and keyboard interactions using existing primitives.

5. Connect server data through the project's canonical client/query layer with cancellation and error mapping.

6. Implement responsive visuals using shared design tokens/components.

7. Test component behavior plus route/API integration and race/error cases.

8. Render and inspect realistic content, accessibility and performance for material paths.

## Implementation patterns

- Keep form input state local to the form unless cross-route persistence is a product requirement.

- Use controlled or framework-recommended form patterns consistently; avoid mixing ownership unpredictably within one form.

- Normalize API errors into display-safe field/global error shapes rather than exposing raw server strings everywhere.

- Use route-level data/loading boundaries where the framework supports them and they match navigation semantics.

- For optimistic updates, define rollback/conflict handling and stable operation identity; optimistic UI is a consistency choice.

- Use memoization only for measured expensive computations or stable identity contracts, not as default ceremony.

- Use semantic native elements and shared accessible primitives for dialogs/menus/tabs rather than per-feature custom interaction code.

- Lazy-load large route/feature dependencies when it reduces startup cost without creating interaction jank.

## Failure modes

- State duplication: props/query/store/local state all copy same object and drift. Pick authority and derive.

- Effect synchronization loop: effects keep two pieces of state in sync. Remove redundant state or move to explicit event.

- Global-state reflex: a local modal/form value enters app-wide store. Keep ownership narrow.

- Stale request overwrite: slower old response replaces current filter/route data. Cancel or identify requests.

- DOM-div UI: click handlers on nonsemantic elements break keyboard/accessibility. Use native/shared primitives.

- Unsafe rich HTML: escaping disabled for convenience. Sanitize with explicit threat model.

- Error blank screen: only successful API shape is handled. Design loading/empty/error states.

- Performance folklore: memoization/virtualization complexity added without traces. Measure first.

## Verification

- Exercise user flow through success, loading, empty, validation/server error and retry.

- Change filters/routes rapidly and verify obsolete async responses cannot overwrite current state.

- Run keyboard/focus/accessibility checks on all interactive components.

- Inspect responsive rendered states with long content and realistic list size.

- Run component/integration tests against real API mocks/contracts and mutation cache invalidation.

- Measure bundle/render/network behavior when performance is material; compare before/after rather than guessing.

- Verify browser navigation/back/deep link and URL state where applicable.

- Inspect console/network for unhandled rejections, duplicate requests and leaked sensitive data.

## Completion criteria

- State ownership and server/cache authority are explicit with no unnecessary synchronization copies.

- Async race, loading, empty, error and mutation behavior is intentional.

- Components use accessible semantic primitives and predictable browser/navigation behavior.

- API integration follows stable contracts and invalidation/cancellation rules.

- Rendered responsive/real-content evidence supports visual claims.

- Performance complexity is justified by measurement where introduced.

## Related skills and escalation

- Use `design` and `visual-qa` for visual system/render quality, `accessibility` for interaction semantics.

- Use `api-contracts` for server interface and framework skills (`react`, `vue`, `svelte`) for idioms.

- Use `web-performance` for detailed Core Web Vitals/network/render optimization.

- Escalate when product state ownership/offline/conflict semantics are undefined rather than hiding them in component code.
