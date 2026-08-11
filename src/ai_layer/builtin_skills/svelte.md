---
slug: svelte
description: Svelte/SvelteKit-specific reactivity, server-client boundary, forms,
  and build discipline.
kind: stack
keywords:
- svelte
- sveltekit
- rune
- load
- action
- form
- load function
- form action
- svelte store
- adapter
entry_sections:
- Apply when
- Mandatory rules
---
# Svelte Skill

## Apply when
The project uses Svelte/SvelteKit and components, runes/stores, routes, load/actions, forms, or SSR behavior change.

## Mandatory rules
- Follow the project-pinned Svelte/SvelteKit syntax/version, routing, adapter, and server/client conventions.
- Keep reactive dependencies explicit; avoid side effects in derived state.
- Never keep request-specific mutable state in a shared server module.
- Handle loading/error/invalidation/form and progressive-enhancement behavior intentionally.
- Preserve accessibility and hydration/SSR correctness.

## Decision rules
- Use the project’s chosen runes/legacy/store style consistently instead of mixing paradigms casually.
- Keep privileged data/actions on server boundaries; client state is not an authorization mechanism.
- Reuse existing route/data-loading patterns before adding a second fetch layer.

## Failure modes
Module-global request leakage, duplicate derived state, hydration mismatches, client-only validation for privileged actions, and assumptions about a Svelte version not declared by the project.

## Quality gates
Run configured static/type/tests and production build; exercise relevant server route/form/browser state transitions.
