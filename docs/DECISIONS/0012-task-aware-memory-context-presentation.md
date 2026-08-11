# 0012 — Task-aware Project Knowledge presentation

Status: Accepted for v0.11.2; extended in v0.11.3.

## Context

`memory_context` v0.11.1 used one semantic top-N presentation for every request. That works for ordinary coding tasks, but a Project Knowledge coverage audit needs to know what the knowledge base already contains. It also received compatibility aliases and full Task runtime history, including previous reviewer discovery reasoning, which both consumed context and biased independent reviewers.

## Decision

Keep one authoritative Project Knowledge store but use two small presentation modes:

- ordinary engineering tasks receive semantically relevant VERIFIED cards, relevant durable history/decisions and source pointers;
- broad Project Knowledge audits receive a complete compact VERIFIED inventory, category counts, stale inventory, metadata-only prior knowledge-work history and a compact read-only control-plane contract.

Previous reviewer findings/plans/reasoning are intentionally excluded from independent audit context. Current repository source remains authoritative. `memory` and `project_intelligence` compatibility aliases are removed from `memory_context`; scanner evidence has one canonical surface. Audit scanner hints expose only objective repository hints, not semantic framework/entrypoint candidates.

The mode selector is a bounded presentation discriminator for explicit Project Knowledge audit wording. It does not choose skills, code, tools or implementation relevance and is not a replacement router/classifier.

## Consequences

- Coverage reviewers can see all existing knowledge keys without loading every full card.
- Ordinary tasks retain cheap semantic retrieval.
- Multi-model audits have less anchoring from prior reviewer reasoning.
- Context duplication and read-only control-plane overhead decrease.
- No DB migration, new service or knowledge graph is introduced.

## v0.11.3 continuation extension

Continuation is a third bounded presentation mode, selected only for explicit continuation/resume wording. It does not semantic-search Project Knowledge with generic text such as `continue` or `продолжай`. Instead it returns a compact recent-task summary, compact Task navigation state and directs the host to restore the latest committed WorkSession before attributing prior work.

Scanner-derived facts are emitted only when the deterministic scanner snapshot is current. If freshness is `refreshing`, `initializing`, stale or missing, scanner evidence and scanner-derived project profile are withheld rather than shown as potentially contradictory facts. Continuation suppresses scanner/profile payload even when current because handoff history and current host-native source inspection own that flow.

This remains a deterministic presentation discriminator, not a domain relevance router or LLM classifier.
