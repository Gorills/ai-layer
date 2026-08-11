# ADR 0003 — Verification, provenance and read-only enforcement

**Status:** accepted for the v0.9.0 candidate.

## Context

Worker self-reports are not verified evidence, reviewer prompts cannot enforce read-only behavior, and changes cannot be attributed to a worker after they already exist. A delegated worker may also disappear without an explicit host disconnect callback, so durable work cannot rely on chat/session lifetime.

## Decision

Bind workers before mutation; use explicit adoption for pre-existing work; snapshot repository state and invalidate read-only stages that mutate it; separate `reported`, `host_verified` and `ai_layer_verified`; persist executable verification evidence and finding verification history. Delegated stages own a bounded durable worker lease with heartbeat timestamps. The machine control plane periodically reaps expired leases: a clean repository creates a fresh unbound stage of the same kind, while repository changes or missing recovery evidence block automatic progress and require an explicit recovery/adoption path.

## Consequences

Disconnects and lease expiry cannot silently rebind provenance. Restart/reconnect behavior is based on durable state rather than chat history. Fixers cannot close their own findings; independent verification/review remains authoritative.
