---
slug: javascript
description: JavaScript runtime, async, module, browser-state and error-handling discipline.
kind: stack
keywords:
- javascript
- js
- promise
- async
- event
- module
- browser
- await
- event listener
- fetch
entry_sections:
- Apply when
- Core contract
---
# JavaScript Skill

## Apply when
JavaScript runtime behavior, browser/client logic, asynchronous effects, modules, events or Node-compatible JS changes.

## Core contract
- Follow the project's runtime target, module system, formatter/linter and build tool.
- Keep async ownership explicit: handle cancellation/stale responses where user actions can supersede requests, and surface expected failures.
- Clean up listeners, observers, timers and subscriptions according to lifecycle ownership.
- Do not duplicate server/derived truth across mutable client stores without a reason.
- Prefer existing platform/project utilities over adding a package for small behavior.

## Data and errors
Validate untrusted external shapes at boundaries when correctness/security depends on them. Do not silently coerce unknown values into valid domain state. Catch errors where the layer can recover or translate them; preserve useful cause/context without leaking secrets.

## Browser behavior
Use native platform semantics before custom abstractions. Avoid layout measurement loops and synchronous heavy work on interaction paths. Make race behavior deterministic instead of assuming requests finish in order.

## Verification
Run configured lint/tests/build and exercise user-visible success/error/loading/race paths at the relevant browser/runtime boundary.
