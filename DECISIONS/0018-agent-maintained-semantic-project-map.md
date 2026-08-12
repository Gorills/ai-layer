# ADR 0018 — Agent-maintained semantic Project Map

## Status

Accepted for 0.13.1.

## Context

The 0.13.0 Project Map intentionally stores scanner-derived navigation metadata rather than source bodies. That gives cheap paths, symbols, imports and coarse purposes, but deterministic extraction alone cannot reliably connect natural-language product/domain requests to the code locations agents discover during real engineering work.

Running a separate LLM mapper after every change would duplicate source reading the coding agent has already performed, increase cost, and recreate an execution layer above the host runtime. At the same time, allowing agents to overwrite scanner-owned navigation would make structural facts untrustworthy.

## Decision

Project Map has two ownership layers:

- the deterministic scanner owns structural navigation such as paths, languages, symbols, imports, routes, hashes and scanner metadata;
- agents may add bounded semantic navigation through `project_map_reconcile` only after real source work has established useful breadcrumbs.

Semantic enrichment is stored separately from structural navigation and is bound to the source content hash from which it was learned. A later source change does not silently rewrite the enrichment: hash mismatch marks it stale and search down-ranks it until a later task reconciles the affected area.

Task completion surfaces a bounded reconciliation opportunity when meaningful navigation knowledge was learned. MICRO/cosmetic work may skip it. The final Task of an Epic must produce task-linked `ProjectMapReconciled` evidence for an explicit affected scope before the Epic can close; an already-correct map may be acknowledged with a factual no-change reason instead of invented entries.

Canonical semantic descriptions are concise English so they align with ordinary source identifiers. Source identifiers are preserved exactly as written. `domain_terms` may retain materially useful Russian or other user/project vocabulary. `project_search` accepts Russian, English, or mixed queries directly; agents must not spend a separate step translating queries before search.

Project Map remains navigation, not behavioral truth. Current repository source is authoritative. Reviewed behavioral invariants remain Project Knowledge and are not moved into Project Map.

Semantic retrieval is fail-soft: embedding/vector failure must not make structural/lexical Project Map navigation unavailable.

## Consequences

- Project Map improves from real Tasks/Epics without a duplicate background mapper.
- Scanner-owned facts cannot be overwritten by agent-authored semantics.
- Cross-language user vocabulary can become a lexical fallback as well as multilingual embedding input.
- Staleness is explicit and source-version-derived instead of hidden behind generated summaries.
- Epic closure now preserves navigation quality as a durable completion artifact alongside documentation and reviewed Knowledge.
- Search/reconciliation remain separate production modules so Project Map growth stays within architecture maintainability limits.
