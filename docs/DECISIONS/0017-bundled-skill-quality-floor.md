# ADR 0017: Enforce a production quality floor for bundled project skills

- **Status:** Accepted, amended 2026-08-12
- **Date:** 2026-08-12
- **Scope:** `src/ai_layer/builtin_skills`, `scripts/skill_gate.py`

## Context

AI Layer ships managed project skills. They are not decorative documentation: an agent uses a skill because it needs domain guidance that should materially improve implementation and verification quality. The earlier catalog satisfied routing contracts, but many files were short enough to act as reminders rather than professional playbooks.

The native-first architecture separates discovery from activation. Supported hosts own relevance selection from compact routing metadata, while AI Layer owns the authoritative skill body. A selected native skill now publishes the complete professional body into its host-compatible `SKILL.md`; exact-section `skill_get(...)` retrieval remains available for explicit rereads, packages, diagnostics and other narrow access. This lets source skills remain deep without forcing the whole catalog into model context before relevance is known.

A purely editorial convention is insufficient. Future maintenance could silently shrink a skill back to a routing stub, omit operational sections, or clone a generic template across multiple domains while still satisfying frontmatter checks.

## Decision

Bundled production skills must satisfy an executable quality floor in `scripts/skill_gate.py` in addition to the existing native-first metadata and publication contract.

The floor requires each bundled skill to:

1. contain at least 7,000 characters and 850 words;
2. expose at least 10 selectively retrievable level-2 sections;
3. include the production sections `Apply when`, `Core contract`, `Evidence to inspect`, `Decision rules`, `Workflow`, `Implementation patterns`, `Failure modes`, `Verification`, `Completion criteria`, and `Related skills and escalation`;
4. use exactly `Apply when`, `Core contract`, and `Decision rules` as the entry sections used by explicit `core` retrieval;
5. keep each required section substantive rather than present-but-empty or token-sized;
6. remain sufficiently distinct from every other bundled skill, using a conservative token-set Jaccard ceiling of 0.75 as a regression detector.

These values are a **minimum safety floor, not a quality score**. Passing the gate does not prove that a skill is expert-level. Domain-specific editorial review, realistic decision rules, failure modes, implementation patterns, and verification guidance remain mandatory.

The floor applies only to AI Layer's managed bundled catalog. It does not reject user-authored or imported skills merely because they are shorter.

## Corpus policy

Shared structure is intentional because weak models benefit from predictable navigation. Shared prose is not. Each skill must contain subject-specific decision logic and verification relevant to its domain or stack.

Cross-cutting concepts may repeat where they are genuinely required (for example idempotency in webhooks and external integrations), but a skill must not be a renamed copy of another skill. Closely related frameworks may share architectural concepts while still providing framework-specific lifecycle, API, testing, deployment, and failure guidance.

The quality floor protects against regression; it does not encourage padding. Content that exists only to satisfy character or word thresholds violates the intent of this decision even if the gate cannot detect it mechanically.

## Context-economy policy

Token economy is applied **before relevance**, not by degrading an already selected professional tool:

- the host sees compact routing metadata for discovery;
- irrelevant skills remain unloaded;
- once a skill is activated, its complete authoritative body is available in the native `SKILL.md`;
- `skill_get(section=...)` can selectively reread one exact topic without requiring the whole skill again;
- `core` retrieval must preserve complete semantic sections and must never cut text at an arbitrary character boundary.

## Consequences

- The bundled catalog, native skill files and release wheel are larger on disk.
- Prompt cost remains bounded primarily because only relevant skills are activated; the entire corpus is never injected by `memory_context`.
- An activated skill intentionally costs more context than the old pointer descriptor because the weak model receives the professional guidance it selected.
- Adding or materially reducing a bundled skill requires enough domain content to pass the floor.
- Generic templating across skills becomes visible to CI through distinctiveness checks.
- Governance baseline must be intentionally refreshed when the skill quality gate changes because `scripts/skill_gate.py` is governance-sensitive.

## Verification

The change is accepted only when:

- the complete bundled catalog passes `scripts/skill_gate.py`;
- tests prove that the shipped catalog passes, a shallow bundled skill fails, and a near-duplicate bundled skill fails;
- native skill tests prove that host-compatible activation files contain the complete canonical body;
- tests prove that `core` retrieval preserves complete entry sections instead of character clipping;
- deterministic release wheel and release manifest are refreshed;
- canonical `make quality` passes in CI;
- the change is reviewed through a pull request before reaching `main`.

## Alternatives considered

### Keep quality editorial-only

Rejected. The repository already treats bundled skills as production agent infrastructure, and an unenforced convention can regress without a visible failure.

### Enforce only file size

Rejected. Size alone is easy to satisfy with padding and does not guarantee useful retrieval structure or distinct domain content.

### Publish only thin pointer descriptors

Rejected. It saves context after relevance has already been established and forces weak models to make a second content-routing decision before they receive the professional guidance they need.

### Auto-inject full skills in `memory_context`

Rejected. That would reintroduce eager loading before host relevance selection and duplicate native Agent Skills behavior.

### Apply the same floor to imported/user skills

Rejected. The repository controls the quality of its bundled catalog but should not prevent users from maintaining intentionally narrow local skills.
