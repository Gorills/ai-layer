---
slug: fastapi
description: FastAPI-specific dependency, validation, async, lifespan, and HTTP contract
  discipline.
kind: stack
keywords:
- fastapi
- pydantic
- dependency
- lifespan
- uvicorn
- starlette
- dependency injection
- depends
- apirouter
---
# FastAPI Skill

## Apply when
The project uses FastAPI and routes, dependencies, Pydantic models, middleware, lifespan, or async services are changed.

## Mandatory rules
- Keep route handlers thin: validate/authorize/map HTTP at the edge and delegate application behavior.
- Reuse dependency providers for scoped DB/session/client/auth resources; ensure cleanup on exceptions/cancellation.
- Do not run blocking database/network/file work directly on the event loop unless the library is genuinely async.
- Preserve Pydantic/request/response schema and status/error contracts unless explicitly changed.
- Initialize long-lived resources in the project’s lifespan/app lifecycle rather than ad-hoc globals.

## Decision rules
- Async endpoints are not automatically better; match the actual I/O libraries and existing architecture.
- Use explicit response models/contracts for public APIs where the project does so.
- Authentication dependencies establish identity; authorization still belongs at the protected action/resource boundary.

## Failure modes
Opening DB clients per request without cleanup, blocking `requests`/sync ORM inside async handlers, business logic in routers, leaking internal validation errors, and hidden mutable module globals.

## Quality gates
Exercise route contract plus service behavior; run configured FastAPI/Python tests and real integration checks for persistence/protocol boundaries.
