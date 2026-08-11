---
slug: react
description: React-specific component, hook, effect, state, accessibility, and build
  discipline.
kind: stack
keywords:
- react
- jsx
- tsx
- hook
- useeffect
- component
- next
- usestate
- nextjs
- react query
entry_sections:
- Apply when
- Mandatory rules
---
# React Skill

## Apply when
The project uses React/Next and components, hooks, client state, rendering, forms, or browser behavior change.

## Mandatory rules
- Follow the project React/Next version, rendering model, routing, data-fetching, state, and styling conventions.
- Keep render pure; use effects only to synchronize with external systems, not for derivable state.
- Respect hook dependency/lifecycle semantics and clean up subscriptions/listeners/timers.
- Keep state as local as practical and do not mirror server/derived state unnecessarily.
- Preserve semantic controls, focus behavior, labels, and keyboard interaction.

## Decision rules
- Prefer derived values/event handlers over effect-driven synchronization.
- Extend existing component/design-system APIs before cloning UI.
- In SSR/server-component projects, keep server/client boundaries explicit and avoid browser-only assumptions on the server.

## Failure modes
Effect loops, stale closures, global context for local state, mutation, unstable keys, fetching the same server state through parallel mechanisms, and hydration mismatches.

## Quality gates
Run configured type/static/tests and production build; verify user-visible async/error/accessibility behavior at the relevant browser boundary.
