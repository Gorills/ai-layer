---
slug: webhooks
description: Webhook verification, replay, idempotency, ordering, and acknowledgement
  discipline.
kind: capability
keywords:
- webhook
- callback
- signature
- event
- replay
- delivery
- event delivery
- webhook secret
- event id
- webhook handler
- вебхук
- колбэк
- подпись webhook
---
# Webhooks Skill

## Apply when
Receiving or processing provider callbacks/webhooks/events is part of the task.

## Mandatory rules
- Verify authenticity using the provider/project-defined signature mechanism on the exact required raw payload before trusting event data.
- Bound body size and parsing; reject malformed or unverifiable events.
- Assume duplicate delivery and define idempotency using a stable provider event/payment identifier or project invariant.
- Separate acknowledgement latency from expensive processing when the existing architecture supports it.
- Store/compare only the minimum event data required; never log secrets or unnecessary sensitive payloads.

## Decision rules
- CSRF exemptions do not replace webhook authentication.
- Return success for an already-processed legitimate duplicate when provider semantics expect idempotent acknowledgement.
- Ordering cannot be assumed unless the provider guarantees it; reconcile against authoritative state when necessary.

## Failure modes
Parsing before signature validation when raw bytes matter, replayable events, duplicate side effects, trusting event status blindly, exposing signature secrets, and retry loops that amplify provider redelivery.

## Quality gates
- Invalid signature, duplicate event, malformed body, and normal delivery are tested.
- Side effects remain correct under repeated delivery.
- Provider-specific acknowledgement/retry semantics are verified against the project/provider contract.
