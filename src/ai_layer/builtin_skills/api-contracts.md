---
slug: api-contracts
description: Public API contract design and compatibility discipline.
kind: capability
keywords:
- api
- contract
- endpoint
- schema
- response
- request
- versioning
- compatibility
- api contract
- public api
- request schema
- response schema
- status code
- version
- pagination
- openapi
- graphql
- контракт api
- публичн api
- схема ответа
- эндпоинт
---
# API Contracts Skill

## Apply when
A public/internal API contract, endpoint schema, status/error semantics, pagination, or versioned interface changes.

## Mandatory rules
- Inspect existing callers, schemas, error shapes, and versioning conventions before changing the contract.
- Treat names, types, nullability, status codes, pagination, idempotency, and error codes as contract surface.
- Validate at the boundary and keep domain errors distinct from transport mapping.
- Preserve backward compatibility unless the task explicitly authorizes a breaking change and its migration path.

## Decision rules
- Additive optional fields are usually safer than changing/removing existing required fields.
- Reuse the project’s established envelope/versioning/error convention; do not introduce a second API style.
- If several incompatible public designs are plausible, check recorded decisions before selecting one.

## Failure modes
Silent response-shape drift, leaking internal exceptions, ambiguous null/missing semantics, unbounded collection endpoints, duplicated versioning conventions, and tests that validate only implementation objects rather than wire behavior.

## Quality gates
- Contract tests cover success plus representative validation/error behavior.
- Existing callers/clients remain compatible or an explicit migration is documented and verified.
- Generated/open API schema is updated when the project uses one.
