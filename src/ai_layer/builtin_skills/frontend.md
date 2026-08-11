---
slug: frontend
description: Frontend architecture, state, async behavior, semantics and responsive
  user-state discipline across frameworks.
kind: domain
keywords:
- frontend
- ui
- component
- form
- accessibility
- browser
- client
- css
- state
- button
- click
- responsive
- loading
- modal
- интерфейс
- кноп
- форм
- клиент
entry_sections:
- Apply when
- Core contract
---
# Frontend Skill

## Apply when
Browser UI behavior, components, state, forms, rendering, navigation or responsive interaction changes.

## Core contract
- Read the frontend/design profile and reuse existing routing, state/data-fetching, component library, tokens and styling conventions before adding alternatives.
- Separate server state, local interaction state and derived state; do not synchronize duplicate truths through effects/watchers without necessity.
- Loading, empty, error, success, disabled, retry and stale-response behavior are functional states, not optional polish.
- Preserve semantic HTML, keyboard/focus behavior and accessible labels. Privileged validation/authorization remains server-side.
- Clean up listeners/timers/subscriptions and handle async races when a newer user action can supersede an older result.
- Visible changes require real render/responsive inspection when tooling permits.

## Components
Keep component APIs cohesive. Extend an established reusable component before cloning a near-duplicate, but do not create giant universal components with dozens of mode flags. Separate data/behavior from presentation only where the current architecture benefits.

## State and data
Prefer derived state to duplicated stored state. Do not fetch/cache the same server resource through competing mechanisms. Make mutation success/error/rollback/refetch behavior explicit. Avoid global stores for purely local UI state.

## Forms and interaction
Use semantic controls, labels and error associations. Disable/prevent duplicate destructive submits where necessary but still rely on server-side idempotency/invariants for correctness. Preserve entered data and actionable errors on recoverable failure where product behavior expects it.

## Rendering and performance
Avoid work in render/template paths that scales badly with list size or causes repeated requests. Stable keys/identities should reflect real domain identity. SSR/hydration projects must keep server/client assumptions explicit.

## Quality gate
Run configured type/static/tests/build and inspect user-visible success/failure/loading/focus/responsive states. Use visual-qa for material layout/design changes.
