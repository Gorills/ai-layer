---
slug: data-consistency
description: Concurrency, idempotency, uniqueness, retry, and multi-write invariant
  discipline.
kind: capability
keywords:
- concurrency
- idempotency
- race
- consistency
- uniqueness
- duplicate
- retry
- atomic
- concurrent
- idempotency_key
- double click
- double-click
- integrityerror
- lock
- конкурент
- гонк
- дубл
- идемпот
- уникальн
---
# Data Consistency Skill

## Apply when
Concurrent requests, duplicate delivery, retries, uniqueness, multi-step writes, or cross-record invariants can affect correctness.

## Mandatory rules
- Define the invariant first: what must remain true under duplicate and concurrent execution?
- Enforce uniqueness/ownership in the strongest practical shared boundary, usually the database for persistent invariants.
- Make retry/idempotency semantics explicit; a retryable operation must not duplicate irreversible side effects.
- Keep check-and-write operations atomic or protected by a constraint/lock appropriate to the access pattern.

## Decision rules
- Prefer unique constraints/upserts/transactional state transitions over process-local flags for cross-request correctness.
- Handle expected conflict errors as domain outcomes; do not swallow unrelated integrity failures.
- External side effects plus DB state need a deliberate ordering/idempotency strategy rather than hope.

## Failure modes
Check-then-insert races, process-local deduplication in multi-worker systems, blind retries, broad exception handling around integrity errors, and tests that exercise only sequential execution.

## Quality gates
- Duplicate/concurrent execution is tested where feasible.
- The invariant survives worker/process boundaries relevant to production.
- Failure after each important step has a defined recoverable outcome.
