---
slug: backend
description: Backend implementation discipline for use cases, data boundaries, concurrency, failure handling, observability and production-safe APIs.
kind: domain
keywords:
- backend
- service
- application logic
- transaction
- concurrency
- queue
- worker
- api
- reliability
- observability
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Backend Engineering Skill

## Apply when

Use for server-side features, business workflows, persistence-backed operations, background jobs, service endpoints and changes where correctness depends on transaction, concurrency, retry or failure semantics. Combine with the framework-specific skill when Django, FastAPI, Laravel, Node or another stack is present.

## Core contract

- Model the business operation before the endpoint. HTTP handlers, CLI commands and workers are transports into the same use case, not separate places for business rules.

- Define authoritative state, invariants and mutation ownership. A backend feature is incomplete if two writers can violate the same invariant differently.

- Make transaction boundaries deliberate and as small as correctness permits; do not hide network calls inside database transactions.

- Assume retries, duplicate delivery, concurrent requests, timeouts and partial external failure whenever the environment can produce them.

- Validate at the trust boundary, normalize once, then keep internal types/invariants stronger than raw transport dictionaries.

- Return stable domain/application errors and map them to transport responses at the edge. Do not expose arbitrary database or SDK exceptions.

- Keep request-path work bounded. Move expensive or unreliable work asynchronous only when the product semantics tolerate delayed completion.

- Observability belongs to the use case: structured logs, correlation, meaningful metrics and durable state transitions should explain what happened without reading raw database rows.

- Optimize from measured bottlenecks and query plans; do not cache or distribute a simple correct flow merely because scale might arrive.

- A production-safe implementation includes migrations, rollback/mixed-version behavior and operational failure handling when those are affected.

## Evidence to inspect

- Endpoint/router/controller definitions and the service/use-case functions they call.

- Database models, repositories/query layer, migrations, indexes and transaction helpers.

- Workers, queues, scheduled jobs, retry policies, dead-letter handling and idempotency mechanisms.

- Error models, middleware, authentication/authorization boundaries and validation schemas.

- Existing logging, tracing, metrics, health checks and runbooks around the capability.

- Tests that exercise the same business operation through different transports or under concurrency.

## Decision rules

- If multiple entry points perform the same operation, route them to one application use case rather than cloning logic.

- If a request may be retried by client, proxy, queue or operator, decide whether the operation is naturally idempotent or needs an idempotency key/deduplication record.

- If correctness depends on read-then-write, use a database constraint, lock, atomic update or optimistic version check rather than trusting single-threaded code.

- If an external call must correspond reliably to a local commit, choose an outbox/worker or explicit compensation strategy instead of pretending one transaction covers both systems.

- If a query returns an unbounded collection, add pagination/streaming and deterministic ordering before production use.

- If a background job can run twice, make its effects idempotent and record durable progress at restart-safe boundaries.

- If caching is proposed, define key ownership, invalidation, freshness tolerance and fallback first; otherwise keep the source-of-truth query.

- If a handler needs many unrelated repositories/services, inspect whether orchestration belongs in an application service.

## Workflow

1. Trace the existing request/job from transport to persistent and external side effects; identify the canonical use case.

2. Write the invariant and success/failure contract, including authorization, validation, idempotency and concurrency expectations.

3. Choose transaction and consistency boundaries; decide what happens on timeout, retry, duplicate delivery and partial downstream failure.

4. Implement the use case behind a narrow input/output contract, keeping transport and persistence translation at their edges.

5. Add database constraints/indexes and migration steps that enforce correctness independently of process-local checks.

6. Add observable state transitions and structured context sufficient to diagnose success, rejection, retry and permanent failure.

7. Test the business path directly, then through its transport, then under the failure/concurrency cases that matter.

8. Inspect query count/plan and request/job timing for new hot paths before declaring the feature complete.

## Implementation patterns

- Use commands/use-case objects or focused service functions when they make transaction and orchestration ownership explicit; avoid giant generic service classes.

- Prefer database uniqueness/check/foreign-key constraints for durable invariants and translate violations into stable application errors.

- Use optimistic concurrency for low-contention editable resources; use row/advisory locking only when the contention and invariant justify serialization.

- Use transactional outbox when a committed local change must eventually publish work/event without a lost-message window.

- Workers should checkpoint durable progress and separate retryable failures from permanent validation/business failures.

- Pagination should use stable sort keys; cursor/keyset pagination is often preferable for large, changing datasets.

- Bulk operations should make partial-success semantics explicit rather than returning a vague 200 after silently skipping failures.

- Health endpoints should distinguish process liveness from readiness/dependency ability according to the deployment platform's needs.

## Failure modes

- Fat controller: business branching, transactions and retries live in the HTTP handler. Extract a transport-independent use case.

- Check-then-insert race: application code verifies absence then inserts without a constraint. Add an authoritative uniqueness/locking mechanism.

- Network-in-transaction: a slow vendor call holds locks and amplifies failure. Commit intent first and perform remote work safely outside the transaction.

- Blind retries: every exception is retried and permanent failures loop forever. Classify retryable/transient versus terminal failures.

- Unbounded query/result: an endpoint is fine on test data but collapses with production cardinality. Bound and paginate.

- Silent partial failure: multi-step work commits some effects and loses the rest. Add atomicity, compensation or durable resumable state.

- Exception leakage: raw SQL/SDK exceptions become client-visible 500 details. Map at boundaries and log safely.

- Observability by prose logs: debugging requires grepping arbitrary strings. Emit structured identifiers, outcome, duration and state transition.

## Verification

- Run unit/use-case tests for invariants and error contracts without requiring transport where possible.

- Run endpoint/worker integration tests against the actual persistence layer for transaction and constraint behavior.

- Exercise duplicate requests/jobs and concurrent mutation when the operation is not trivially read-only.

- Inject downstream timeout/failure and verify local state, retry policy and user-visible outcome remain coherent.

- Inspect generated SQL/query count and explain plans for new or changed high-cardinality paths.

- Verify logs/metrics contain correlation identifiers and do not expose secrets or sensitive payloads.

- Check pagination boundaries, empty results, maximum payloads and deterministic ordering.

- Verify migrations and mixed-version deployment behavior when schema or persisted state changes.

## Completion criteria

- The business operation has one canonical implementation independent of transport.

- Durable invariants are enforced at the strongest practical layer and concurrency behavior is defined.

- Transaction, retry, idempotency and partial-failure semantics are explicit and tested where relevant.

- Endpoints/jobs are bounded in work and data volume or intentionally streamed/asynchronous.

- Errors are stable, observable and safe; raw infrastructure exceptions do not define the public contract.

- Production diagnostics can explain the operation without ad hoc database archaeology.

- Performance and data-access behavior were checked with realistic cardinality for material paths.

## Related skills and escalation

- Use `api-contracts` for externally consumed endpoint schemas and compatibility.

- Use `database`, `database-migrations` and `data-consistency` for persistence-heavy changes.

- Use `webhooks` or `external-integrations` for inbound/outbound third-party reliability.

- Use framework stack skills for idiomatic implementation after these backend semantics are decided.
