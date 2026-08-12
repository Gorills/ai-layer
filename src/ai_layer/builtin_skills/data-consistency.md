---
slug: data-consistency
description: Consistency engineering for invariants, transactions, concurrency, idempotency, replication, events and reconciliation across durable state.
kind: capability
keywords:
- consistency
- transaction
- concurrency
- idempotency
- outbox
- eventual consistency
- locking
- reconciliation
- invariant
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Data Consistency Skill

## Apply when

Use when one business fact is written or derived in multiple places, when concurrent requests can race, when queues/events/external systems participate, or when partial failure could leave durable state contradictory.

## Core contract

- Write the invariant first: what facts must never contradict, which source is authoritative and when temporary divergence is acceptable.

- Use the strongest atomicity mechanism that actually covers the state being changed; do not pretend a database transaction covers remote services.

- Enforce durable invariants with database constraints/atomic operations where practical, not only process-local prechecks.

- Assume concurrent writers and retries. Correctness that depends on “requests usually do not overlap” is not a consistency design.

- For asynchronous propagation, define delivery semantics, idempotency, ordering assumptions, lag tolerance and reconciliation.

- Choose one source of truth per fact. Derived caches/read models should be rebuildable or reconcilable from authority.

- Make state transitions explicit for multi-step workflows so recovery can distinguish not-started, in-progress, committed and terminal failure.

- Design duplicate handling before publishing jobs/events/webhooks; at-least-once delivery without idempotent effects creates duplicate business actions.

- Avoid distributed locks unless their failure/lease semantics are understood and necessary; often local DB constraints or ownership partitioning are safer.

- Observability should expose invariant violations, backlog/lag and reconciliation outcomes before users discover divergence.

## Evidence to inspect

- Tables/entities and every code path that writes the same logical fact.

- Constraints, indexes, transaction isolation/locking and optimistic version fields.

- Queues/events/outbox/inbox tables, retry/deduplication keys and ordering/partition keys.

- Caches/search/read models and their invalidation/rebuild/reconciliation behavior.

- External APIs involved in multi-step workflows and their idempotency/transaction semantics.

- Known repair scripts or incident history indicating prior divergence.

## Decision rules

- If an invariant fits one database, enforce it there with a transaction/constraint/atomic update before introducing distributed coordination.

- If read-then-write can race, replace application precheck with constraint, compare-and-swap/version, lock or atomic conditional update.

- If a local commit must reliably trigger asynchronous work, use transactional outbox or equivalent atomic intent recording.

- If a consumer can receive duplicates, make the business effect idempotent and persist deduplication at the same authority needed for correctness.

- If event order matters, partition/sequence by the entity or encode monotonic version and reject/stage stale updates.

- If temporary divergence is accepted, define maximum tolerated lag and reconciliation source/process.

- If two systems both claim authority for the same field, redesign ownership or define an explicit conflict-resolution protocol.

- If manual repair is possible, make repair idempotent, auditable and safe under concurrent normal traffic.

## Workflow

1. List the business invariants and map each involved durable representation/writer.

2. Identify atomic boundaries and failure windows, including network/timeouts between systems.

3. Choose authoritative source and synchronization model for each derived representation.

4. Design concurrency control, idempotency keys and event/order semantics.

5. Implement durable state transitions/outbox/deduplication close to the authoritative transaction.

6. Add reconciliation/repair path for any intentionally eventual or externally coordinated state.

7. Test concurrent, duplicate, reordered and partial-failure scenarios deterministically.

8. Add monitoring for lag, repeated retries, invariant violations and reconciliation failure.

## Implementation patterns

- Unique/check/foreign-key constraints provide strong last-line invariants and should be translated into domain/application conflicts.

- Optimistic version columns work well for user edits and low-contention updates where retries are acceptable.

- Transactional outbox closes the local commit versus publish gap; consumers still need duplicate-safe processing.

- Inbox/deduplication records should be committed atomically with the consumer's business effect when duplicate prevention matters.

- State machines make multi-step workflow recovery explicit; transitions should reject impossible source states.

- Reconciliation compares authority to projection/external state and applies bounded idempotent corrections with audit.

- Cache invalidation should follow authoritative mutations and tolerate missed invalidations via TTL/versioning/rebuild as appropriate.

- For counters/aggregates, prefer atomic database operations or append/event aggregation over read-increment-write races.

## Failure modes

- Check-then-act race: two workers pass the precheck. Move invariant to atomic/constraint mechanism.

- Distributed transaction fantasy: DB commit and vendor call are treated as one operation. Add intent/compensation/reconciliation.

- Duplicate consumer effect: retries create two records/payments/emails. Persist idempotency around the effect.

- Order assumption: queue normally orders messages but retries/partitions violate it. Encode entity sequence/version.

- Dual authority: user edits value in two systems and last-writer-wins accidentally. Assign ownership/conflict rule.

- Forever inconsistency: eventual consistency has no lag SLO or reconciliation. Define both.

- Repair race: manual script overwrites newer valid state. Use conditional/versioned idempotent repair.

- Cache-as-truth: loss/eviction makes durable state unknowable. Keep reconstructable authority.

## Verification

- Run concurrent operations against the real database and assert the invariant under collision.

- Replay identical commands/events/jobs and confirm business effects are not duplicated.

- Inject failure between each multi-system step and verify recovery/reconciliation reaches a known state.

- Deliver events out of order/stale where the transport permits and verify version/order handling.

- Inspect constraints/transaction scope and ensure network calls do not accidentally extend locks.

- Run reconciliation on already-correct and divergent data to prove idempotence and bounded correction.

- Measure/inspect lag/backlog diagnostics for eventual projections.

- Verify operational repair can be audited and does not bypass normal invariants.

## Completion criteria

- Every material invariant has an authoritative owner and enforcement mechanism.

- Concurrency, retry, duplicate and partial-failure behavior is explicit.

- Cross-system atomicity gaps have durable intent, compensation or reconciliation rather than wishful transactions.

- Derived state can be rebuilt/reconciled from authority.

- Failure-path tests demonstrate invariant preservation or bounded eventual recovery.

- Operators can detect and repair divergence safely.

## Related skills and escalation

- Use `database` and `database-migrations` for local persistence mechanics.

- Use `webhooks`/`external-integrations` for third-party delivery and idempotency.

- Use `backend` for use-case transaction boundaries and `testing` for deterministic races.

- Escalate when business ownership/conflict resolution cannot be inferred from code.
