---
slug: vue
description: Vue-specific reactivity, component, SSR, async-state, and build discipline.
kind: stack
keywords:
- vue
- nuxt
- composition api
- ref
- reactive
- computed
- watcher
- watch
- pinia
entry_sections:
- Apply when
- Mandatory rules
---
# Vue Skill

## Apply when
The project uses Vue/Nuxt and components, composables, reactivity, routing, state, or SSR behavior changes.

## Mandatory rules
- Follow the installed Vue/Nuxt version and Composition/Options API conventions already present.
- Keep reactive ownership explicit; avoid destructuring that accidentally loses reactivity.
- Prefer `computed`/derived state over watchers that synchronize duplicate values.
- Clean up external listeners/subscriptions and handle stale async work.
- Preserve component contracts, accessibility, loading/error states, and SSR/hydration boundaries where applicable.

## Decision rules
- Keep local state local; use project state tooling only for genuinely shared state.
- Do not mutate props or create hidden cross-component state.
- Reuse existing composables/components before adding a parallel abstraction.

## Failure modes
Broad watchers, accidental non-reactive copies, side effects in computed state, module-global request state in SSR, hydration mismatch, and duplicated fetch/state mechanisms.

## Quality gates
Run configured type/static/tests and production build; verify relevant browser/SSR state transitions and accessibility behavior.
