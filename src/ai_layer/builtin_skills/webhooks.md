---
slug: webhooks
description: Webhook receiver and sender discipline for authenticity, replay, idempotency, ordering, retries, durable processing and operational reconciliation.
kind: capability
keywords:
- webhook
- signature
- hmac
- replay
- idempotency
- callback
- event
- retry
- delivery
- outbox
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Webhook Engineering Skill

## Apply when

Use for inbound third-party callbacks or outbound webhook delivery to consumers. Apply whenever an asynchronous HTTP message can be retried, duplicated, delayed, reordered or forged.

## Core contract

- Authenticate the raw message according to the provider/protocol before trusting event fields; parse/transform only after preserving bytes needed for signature verification.

- Assume at-least-once delivery unless the contract proves otherwise. Every handler must tolerate duplicates without duplicating business effects.

- Acknowledge quickly after durable acceptance when long processing is unnecessary in the request; decouple heavy/retryable work via a durable queue.

- Persist provider event/delivery identity and relevant processing state when duplicate prevention/recovery matters.

- Do not assume event order. Use entity versions/timestamps/state-machine guards and ignore/stage stale transitions appropriately.

- Verify timestamp/replay windows where supported, but idempotency remains necessary because legitimate retries can occur within the window.

- Return protocol-appropriate statuses: distinguish authentication/invalid payload from temporary server failure according to sender retry semantics.

- For outbound webhooks, sign messages, bound timeouts, retry with backoff, expose delivery history and stop/recover after terminal exhaustion.

- Do not log raw signed payloads/secrets by default; retain safe event IDs, types, target IDs and verification outcome.

- Maintain reconciliation for important workflows because webhooks can be delayed, lost by misconfiguration or disabled.

## Evidence to inspect

- Provider/consumer authoritative signature and retry documentation, including raw-body requirements and clock tolerance.

- Existing ingress middleware/body parsing that could mutate bytes before verification.

- Event IDs, entity versions and local idempotency/deduplication storage.

- Handler transaction boundary and whether enqueue/business update is durably committed before response.

- Outbound delivery table/queue, signature secret lifecycle and retry policy.

- Reconciliation/polling/manual recovery path for missed events.

## Decision rules

- If signature verification uses raw bytes, capture them before JSON/body middleware normalizes whitespace/encoding.

- If the same event ID can be delivered repeatedly, commit dedupe record atomically with the business effect or durable enqueue.

- If two distinct event IDs can describe the same business transition, protect the business invariant in addition to event-ID dedupe.

- If events can arrive out of order, compare authoritative version/state and reject stale transitions rather than replaying state backwards.

- If processing exceeds a short deterministic boundary, persist/queue then acknowledge rather than making the sender wait through full workflow.

- If invalid signatures are received, fail closed and do not enqueue/process payload fields.

- If outbound consumer is slow/down, isolate its retries from other tenants/targets and apply timeout/backoff/dead-letter limits.

- If missing events would leave money/order/account state wrong, add periodic reconciliation with authoritative source.

## Workflow

1. Read the exact provider/consumer webhook contract and identify signature input, headers, event identity and retry behavior.

2. Design ingress ordering: capture raw body → verify authenticity/replay → parse/validate → dedupe → durable accept/process.

3. Define business idempotency and state-order rules separately from transport dedupe.

4. Implement fast bounded request path and durable asynchronous processing where needed.

5. Map failures to response statuses that cause the desired sender retry behavior.

6. For outbound delivery, persist payload/version/target, sign, send with timeout and record attempts/outcomes.

7. Add replay/duplicate/reorder/invalid-signature tests and crash-window tests around persistence.

8. Add operational delivery/reconciliation visibility and secret rotation procedure.

## Implementation patterns

- Store inbound event ID, provider, received time, processing state and safe diagnostic metadata under a unique constraint.

- Use one transaction for dedupe + local business effect when processing synchronously in one database.

- If enqueueing, transactional outbox/inbox patterns close the commit/enqueue gap.

- State-machine transitions should be monotonic or explicitly validate allowed source states so stale events cannot regress state.

- For outbound payloads, use a versioned canonical serialization before signing so retries reproduce the same signed content.

- Rotate webhook secrets with a bounded overlap of active verification keys if the provider/client supports it.

- Expose delivery attempt count/last status/next retry without storing sensitive headers.

- Reconciliation should use authoritative provider status and be idempotent when applying corrections.

## Failure modes

- Parse-before-signature: framework reserializes JSON and signature never matches or verification uses altered bytes. Verify raw input.

- Event-ID-only safety: provider sends two IDs for same transition and effect duplicates. Enforce business idempotency too.

- Immediate 200 before durable acceptance: process crashes and event is lost. Commit acceptance/effect first.

- Long synchronous handler: sender times out and retries while first attempt still runs. Bound/queue work.

- Order assumption: `created` arrives after `completed` and state regresses. Guard by version/state.

- Signature secret logged: debug header dump leaks verification credential. Redact.

- Retry storm: outbound deliveries retry quickly without jitter/limits. Backoff and isolate targets.

- Webhook-only truth: missed callback leaves permanent stale state. Reconcile important workflows.

## Verification

- Replay identical signed event multiple times and assert one business effect.

- Send distinct events representing duplicate/stale transition and verify invariant/order handling.

- Test invalid signature, expired/replay timestamp, malformed body and missing required headers.

- Crash/fail between dedupe, effect and enqueue boundaries to confirm no lost/duplicate window.

- Verify inbound response codes cause intended retry/no-retry behavior in contract fixtures.

- For outbound, test signature reproduction, timeout, 4xx/5xx, retry exhaustion and dead-letter/manual replay.

- Inspect logs/database for secret/raw sensitive payload leakage.

- Run reconciliation against deliberately missed/stale state and confirm safe correction.

## Completion criteria

- Webhook authenticity is verified before payload trust using the correct raw representation.

- Duplicate, replay and out-of-order delivery cannot violate business invariants.

- Request processing is durably accepted before success response and remains bounded.

- Outbound deliveries have signed, observable, isolated retry lifecycle.

- Missed critical events can be reconciled.

- Adversarial and crash-window tests provide evidence.

## Related skills and escalation

- Use `external-integrations` for provider client/reconciliation and `security` for signature/secret handling.

- Use `data-consistency` for inbox/outbox/state-machine semantics.

- Use `api-contracts` for versioned payload/error contract design.

- Escalate when provider signature/retry semantics are undocumented or unverifiable.
