---
slug: api-contracts
description: Stable API contract engineering for schemas, semantics, errors, pagination, idempotency, compatibility and consumer-verifiable behavior.
kind: capability
keywords:
- api
- contract
- http
- rest
- schema
- pagination
- idempotency
- errors
- versioning
- openapi
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# API Contract Design Skill

## Apply when

Use when adding or changing HTTP/RPC/public service endpoints, SDK-facing payloads, event-like API responses or any interface consumed outside the implementation module. Apply even for internal APIs when separately maintained clients depend on stable semantics.

## Core contract

- An API contract includes behavior, not only JSON shape: authorization, validation, status/error semantics, idempotency, ordering, pagination, side effects and consistency.

- Design from consumer tasks and domain language. Do not expose ORM/vendor structures just because they are convenient to serialize.

- Make optional, nullable, missing, empty and default states distinct where consumers need to distinguish them.

- Use stable machine-readable error codes/types and human-readable messages; clients should not parse prose to make control-flow decisions.

- Keep collection operations bounded and deterministically ordered. Pagination metadata/cursors must have defined stability and invalidation semantics.

- Use HTTP/protocol semantics intentionally rather than returning 200 for every outcome or overloading one endpoint with unrelated commands.

- Idempotency must be explicit for mutating operations that clients/proxies/jobs may retry; duplicate transport delivery should not create duplicate business effects.

- Evolution should be additive where possible. Removing/renaming/changing meaning requires a compatibility/version plan based on actual consumers.

- Document security-relevant behavior: authentication, authorization scope, sensitive fields and whether identifiers can be enumerated.

- Generate/validate machine contracts where supported, but keep behavioral contract tests because a schema cannot prove side effects or concurrency semantics.

## Evidence to inspect

- Existing routes/controllers/schema/OpenAPI/protobuf definitions and client SDK usage.

- Consumer code, frontend queries, integration tests and external documentation that show actual expectations.

- Domain use-case errors and authoritative validation/authorization logic.

- Database ordering/uniqueness and pagination constraints that affect returned semantics.

- Gateway/proxy/cache behavior, timeout limits and idempotency infrastructure.

- Version/deprecation policy and deployment coupling between producer and consumers.

## Decision rules

- If a mutation is naturally retryable but not naturally idempotent, require an idempotency key or operation identity with a defined replay response.

- If consumers need to distinguish absent from null, encode that distinction explicitly and test serialization/deserialization.

- If a list can grow without a known small bound, paginate from the first public release rather than retrofitting after clients depend on full responses.

- If sort order matters, expose/define it explicitly and include a unique tie-breaker for stable pagination.

- If an operation represents a distinct command with unique permissions/failure semantics, prefer a dedicated endpoint/action over magic payload switches.

- If an incompatible semantic change is unavoidable, introduce a new contract/version instead of reusing the old shape with new meaning.

- If one error may be handled differently by clients, give it a stable code/type and appropriate protocol status.

- If sensitive fields are not needed by a consumer, omit them by contract rather than relying on clients not to display them.

## Workflow

1. Identify consumers and the exact user/business operation the API exposes.

2. Write request, response and error examples including empty, invalid, forbidden, conflict and retry/duplicate cases.

3. Define authorization scope, validation ownership, idempotency and side-effect/consistency semantics.

4. Choose resource/action boundaries, protocol methods/statuses and collection ordering/pagination.

5. Implement transport schemas that translate to/from application contracts without leaking infrastructure types.

6. Update machine-readable schema/docs and add producer contract tests plus representative consumer tests when available.

7. Exercise compatibility with existing payloads/clients and mixed versions if changing an established endpoint.

8. Inspect actual serialized responses and error bodies, not only typed internal objects.

## Implementation patterns

- Use resource representations for state and explicit commands/actions for operations that do not fit CRUD semantics cleanly.

- Use cursor/keyset pagination with stable unique ordering for large changing sets; define cursor opacity and invalid-cursor behavior.

- Use optimistic concurrency tokens/version fields for edits where lost updates matter.

- For idempotency records, bind key to operation/actor/request fingerprint as appropriate and return the original committed result on safe replay.

- Represent validation failures as a stable top-level error plus field/path details rather than framework-native exception dumps.

- Keep timestamps/units/time zones explicit and machine-parseable; avoid locale-dependent formats in contracts.

- Use links/identifiers consistently and document whether identifiers are stable, opaque and externally referenceable.

- Treat webhooks/events as separate asynchronous contracts with delivery semantics; do not assume normal request/response guarantees.

## Failure modes

- Schema-only thinking: OpenAPI validates types but error/side-effect semantics drift. Add behavioral contract tests.

- Leaky ORM: internal columns/relations become public fields and block schema evolution. Map to explicit API models.

- Unbounded list: initial convenience becomes memory/latency outage. Paginate and bound filters.

- Error prose contract: clients match text strings. Add stable codes/types and preserve them intentionally.

- Nullable ambiguity: missing/null/empty collapse and clients cannot express updates correctly. Define patch/update semantics.

- Retry duplication: timeout causes client retry and duplicate order/payment/job. Add idempotency at the authoritative operation.

- Pagination instability: offset/sort without tie-breaker duplicates/skips items under concurrent changes. Use deterministic strategy.

- Silent breaking change: field keeps name but meaning/unit changes. Version or compatibility-adapt the semantics.

## Verification

- Validate real serialized requests/responses against the schema, including optional/null/unknown-field behavior.

- Run contract tests for success, invalid, unauthenticated, forbidden, not-found/conflict and server/downstream failure mappings.

- Repeat/replay mutating requests and confirm idempotency semantics where promised.

- Test pagination across ties, empty/final pages and concurrent inserts/updates for the chosen stability promise.

- Run existing consumer/frontend tests and search for field/error/status assumptions before changing established contracts.

- Verify sensitive data is omitted/redacted and authorization cannot be bypassed by object identifiers.

- Check generated docs/schema diff for accidental public changes.

- For versioned changes, test old request/response compatibility or explicitly verify migration/deprecation behavior.

## Completion criteria

- Request, response, error, authorization, idempotency and consistency semantics are explicit.

- Collections are bounded and deterministically ordered where scale can grow.

- Public models do not accidentally expose persistence/vendor internals.

- Compatibility and deprecation are handled for known consumers.

- Machine schema plus behavioral contract evidence cover material paths.

- Actual wire-format inspection matches the declared contract.

## Related skills and escalation

- Use `backend` for use-case/transaction semantics, `authentication`/`authorization` for access control, and `compatibility` for evolution.

- Use `webhooks` for asynchronous inbound/outbound callbacks.

- Use framework skills for schema/router implementation after the contract is defined.

- Escalate when consumer inventory is unknown and a breaking change is being proposed.
