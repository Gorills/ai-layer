# ADR 0020 — Durable Work spine and truthful observability

## Status

Accepted for 0.14.0.

## Context

The Project Intelligence control plane correctly stopped treating managed Tasks as a universal execution permission layer, but the durable model still had no first-class representation of ordinary user work. Dashboard state therefore inferred "working" from managed Task state, MCP bridge activity and short-retention JSONL telemetry. That conflated three different concepts: user work, optional strict assurance, and transport/technical activity.

Project-specific rules also existed outside the normal `project_status` path, and multilingual Project Map retrieval depended too heavily on a model sending a useful raw query. These gaps were especially visible with weak agents and after process/chat restarts.

The repository bootstrap also referenced `docs/DECISIONS/` even though the canonical ADR directory is the root `DECISIONS/`, creating a concrete path by which an otherwise compliant agent could miss accepted architectural decisions.

## Decision

AI Layer separates three identities permanently:

1. **WorkItem** — one substantive user-visible unit of ordinary work. Multiple WorkItems may exist for a project. It records goal, kind, lifecycle, result, reviewed/changed paths, repository delta, checks, Project Map disposition, observability coverage and assurance source.
2. **ManagedTask** — optional strict assurance workflow. Its existing one-open-Task constraint remains scoped to the managed Task engine and is not reused as a WorkItem constraint.
3. **RuntimeEvent / activity** — append-only actions and evidence. Activity never becomes the user-work identity.

`AgentRun` records an observed root-agent/subagent lifecycle for a WorkItem. A run has host/client/session/turn/model identity, heartbeat, terminal state, observability coverage and assurance. A non-stale AgentRun is required before Dashboard may claim ordinary work is live. MCP bridge traffic or an open managed Task alone does not prove user work is currently executing.

Short ordinary work should normally require at most `work_begin` plus one terminal Work call. `work_checkpoint` is reserved for meaningful milestones or blockers. Commands use the existing durable `CommandReceipt`/advisory-lock idempotency boundary rather than a second deduplication mechanism.

Runtime events remain the canonical durable journal. `runtime_event_context` is an additive correlation sidecar that links an event to Work/Run/Task/Epic and host/session/model identity without rewriting historical RuntimeEvent rows. Common MCP execution records one safe terminal `OperationCompleted` or `OperationFailed` event; raw prompt/source bodies are never copied into the human event presenter. Existing JSONL telemetry remains diagnostic only.

`project_status` now carries a bounded effective `project_policy` with contract version and SHA-256 so agents receive project rules through the mandatory startup path and can detect drift.

Project Map search has a bounded retrieval contract. For non-English natural-language intent, the primary query is concise English and code-centric while exact repository identifiers remain verbatim. At most one original-language/mixed variant may widen domain aliases. Returned map entries are breadcrumbs and current source must still be opened before code-truth claims or edits.

The canonical repository ADR location is root `DECISIONS/`; root bootstrap and governance tests must not redirect agents to a historical or nonexistent `docs/DECISIONS/` path.

## Consequences

- Dashboard can distinguish live Work, managed Tasks, Project Map quality and MCP bridges instead of presenting one synthetic "agent working" state.
- Ordinary work survives restart/chat boundaries without forcing every request through the managed Task engine.
- Managed Task semantics and their existing exclusivity constraint remain unchanged.
- Observability claims become explicit: lifecycle-only/control-plane evidence is not presented as full host visibility.
- New host adapters can later improve AgentRun coverage without changing WorkItem identity.
- Project Map closure can later bind semantic reconciliation directly to WorkItem provenance without another Task-engine rewrite.
- Repository agents reliably discover accepted ADRs from the canonical `DECISIONS/` directory.
