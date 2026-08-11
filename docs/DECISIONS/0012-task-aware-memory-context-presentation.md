# 0012 — Task-aware Project Knowledge presentation

Status: Accepted for v0.11.2. The v0.11.3 continuation-specific extension was later removed as unnecessary intent routing.

## Context

`memory_context` v0.11.1 used one semantic top-N presentation for every request. That works for ordinary coding tasks, but a Project Knowledge coverage audit needs to know what the knowledge base already contains. It also received compatibility aliases and full Task runtime history, including previous reviewer discovery reasoning, which both consumed context and biased independent reviewers.

## Decision

Keep one authoritative Project Knowledge store but use two small presentation modes:

- ordinary engineering requests receive semantically relevant VERIFIED cards, relevant durable history/decisions and source pointers;
- broad Project Knowledge audits receive a complete compact VERIFIED inventory, category counts, stale inventory, metadata-only prior knowledge-work history and a compact read-only control-plane contract.

Previous reviewer findings/plans/reasoning are intentionally excluded from independent audit context. Current repository source remains authoritative. `memory` and `project_intelligence` compatibility aliases are removed from `memory_context`; scanner evidence has one canonical surface. Audit scanner hints expose only objective repository hints, not semantic framework/entrypoint candidates.

The mode selector is a bounded presentation discriminator only for explicit Project Knowledge audit wording. It does not choose skills, code, tools, implementation relevance or general user intent and is not a replacement router/classifier.

Natural-language intent remains owned by the host/model. WorkSession recovery stays available through `session_restore`, but `memory_context` does not classify phrases such as `continue`, `resume` or `продолжай` and does not automatically route them to session tools. This avoids duplicating language understanding in AI Layer.

Scanner-derived facts are emitted only when the deterministic scanner snapshot is current. If freshness is `refreshing`, `initializing`, stale or missing, scanner evidence and scanner-derived project profile are withheld rather than shown as potentially contradictory facts. Current repository source remains authoritative.

## Consequences

- Coverage reviewers can see all existing knowledge keys without loading every full card.
- Ordinary requests retain cheap semantic retrieval without a hidden continuation classifier.
- The model can decide from arbitrary natural language whether prior session context matters.
- Multi-model audits have less anchoring from prior reviewer reasoning.
- Context duplication and routing logic decrease.
- No DB migration, new service, intent router or additional state machine is introduced.
