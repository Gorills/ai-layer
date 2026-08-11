# ADR 0010 — Native-source-first verified Project Knowledge

**Status:** accepted for the v0.11.0 candidate.

## Context

AI Layer 0.10.3 still treated repository scanning as both deterministic project evidence and a semantic copy of current source: eligible files were chunked, embedded and returned through `memory_context`. Cursor, Codex and Antigravity already provide native current-code search/read capabilities, while the durable information that is expensive to reconstruct across chats/models is different: project topology, subsystem intent, engineering invariants, accepted decisions, prior work and known limitations.

Automatically generated scanner summaries are also not strong enough to be authoritative semantic documentation. A scanner can reliably establish file identity, hashes, manifests, imports, tests and other evidence, but semantic claims such as subsystem purpose or architecture boundaries require model interpretation and independent review.

The redesign touches the governance-sensitive Task transition path because Project Knowledge publication must be tied to the existing independent REVIEW lifecycle rather than trusting a mapper write directly.

## Decision

Use the following ownership model:

```text
HOST NATIVE TOOLS own discovery/reading of current source.
SCANNER owns deterministic repository evidence and freshness.
AI LAYER PROJECT KNOWLEDGE owns durable reviewed semantic understanding.
TASK ENGINE owns review-gated publication of model-authored knowledge.
```

`scan` no longer builds a semantic current-source index. Pre-v0.11 scanner `file`, `architecture` and `project-intelligence` Knowledge rows are lazily removed when scanner schema v4 refreshes a project. No destructive database reset is required.

Project Knowledge uses the existing `Knowledge` persistence model with a distinct `project-knowledge` kind. Cards are evidence-backed and lifecycle-managed as `DRAFT`, `VERIFIED`, `STALE` or `SUPERSEDED`. Every card cites repository paths captured by deterministic `ProjectFile` evidence and stores their content fingerprints. A source change invalidates only cards whose supporting evidence changed.

A delegated IMPLEMENT/FIX worker may create only DRAFT cards during an explicit review-gated managed task. A passing REVIEW may publish them only after the active reviewer has actually retrieved that task's DRAFT cards through the Project Knowledge read path; this inspection is recorded as a durable `KnowledgeReviewInspected` event. A cancelled task supersedes its unpublished drafts. A reviewed `overview` card is required before the project reports a complete initial knowledge baseline.

Initial legacy onboarding is explicit, not automatic: a strong host model acts as Mapper in a standard managed task, an independent reviewer challenges every evidence-backed claim, the existing FIX/REVIEW loop handles findings, and later independent audit tasks may use other models to challenge coverage. Multiple models are not chained as sequential summary rewriters.

`memory_context` becomes a compact task project brief: relevant VERIFIED cards, relevant durable Task history, relevant decisions, source pointers, stale warnings and small scanner evidence. It never returns current-source chunks. Explicit `memory_search` searches curated Project Knowledge, not repository source.

## Consequences

- Weak models receive navigation/history/invariants without paying repeated context for copied current code.
- Current implementation details remain fresh because agents inspect them with native host tools.
- AI-generated project documentation is not authoritative until independently reviewed.
- Knowledge can become stale without forcing a full knowledge rebuild after every commit.
- Existing durable Task/Decision/session history remains useful and separate from source evidence.
- Scanner inference fields retained for compatibility are explicitly labelled unreviewed evidence.
- No Epic behavior is introduced; repository `epic/*` artifacts are ordinary legacy project evidence until a future AI Layer Epic capability exists.
- The governance baseline for `tasks/transitions.py` must be re-acknowledged only after this ADR, regression tests and human-visible rationale are present. Production trust still requires protected-branch review and canonical quality checks outside this local source archive.
