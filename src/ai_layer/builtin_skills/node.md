---
slug: node
description: Node.js/TypeScript server runtime, async lifecycle, error, and package
  discipline.
kind: stack
keywords:
- nodejs
- node.js
- express
- nestjs
- fastify
- npm
- pnpm
- yarn
- typescript server
- server
- backend
- route
- controller
- middleware
---
# Node.js Skill

## Apply when
JavaScript/TypeScript is used on the server or Node runtime/package behavior is part of the task.

## Mandatory rules
- Follow the project-pinned Node version, module system, TypeScript settings, package manager, lint/test/build commands.
- Keep promise rejection/error propagation explicit; centralize transport error mapping using existing framework conventions.
- Bound outbound I/O and clean up sockets/listeners/timers/resources during shutdown/tests.
- Avoid CPU-heavy synchronous work on request/event-loop paths.
- Do not manually edit lockfiles; use the project package manager.

## Decision rules
- Reuse existing framework DI/service/controller conventions rather than creating a parallel architecture.
- Choose streaming for large payloads and backpressure-sensitive I/O.
- Do not introduce a new runtime validation/state library when the project already has one that fits.

## Failure modes
Unhandled promises, callback/promise double completion, module-system mismatches, process-global mutable request state, blocking crypto/file work on hot paths, and dependency additions without lock/build verification.

## Quality gates
Run configured typecheck/lint/tests/build for changed server code; test failure and shutdown/resource behavior when relevant.
