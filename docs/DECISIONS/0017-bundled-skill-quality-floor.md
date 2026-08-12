# ADR 0017: Enforce a production quality floor for bundled project skills

- **Status:** Accepted
- **Date:** 2026-08-12
- **Scope:** `src/ai_layer/builtin_skills`, `scripts/skill_gate.py`

## Context

AI Layer ships 43 managed project skills. They are not decorative documentation: an agent requests a skill because it needs domain guidance that should materially improve implementation and verification quality. The previous catalog satisfied routing and descriptor contracts, but many files were short enough to act as reminders rather than professional playbooks.

The native-first architecture already separates discovery from authoritative retrieval. Host descriptors stay compact, `skill_get(..., section=...)` can retrieve one level-2 section, and full retrieval remains exceptional. That means the source skills can be materially deeper without forcing the whole corpus into the model context.

A purely editorial convention is insufficient. Future maintenance could silently shrink a skill back to a routing stub, omit operational sections, or clone a generic template across multiple domains while still satisfying frontmatter and native-descriptor checks.

## Decision

Bundled production skills must satisfy an executable quality floor in `scripts/skill_gate.py` in addition to the existing native-first metadata and descriptor contract.

The floor requires each bundled skill to:

1. contain at least 7,000 characters and 850 words;
2. expose at least 10 selectively retrievable level-2 sections;
3. include the production sections `Apply when`, `Core contract`, `Evidence to inspect`, `Decision rules`, `Workflow`, `Implementation patterns`, `Failure modes`, `Verification`, `Completion criteria`, and `Related skills and escalation`;
4. use exactly `Apply when`, `Core contract`, and `Decision rules` as the compact entry sections;
5. keep each required section substantive rather than present-but-empty or token-sized;
6. remain sufficiently distinct from every other bundled skill, using a conservative token-set Jaccard ceiling of 0.75 as a regression detector.

These values are a **minimum safety floor, not a quality score**. Passing the gate does not prove that a skill is expert-level. Domain-specific editorial review, realistic decision rules, failure modes, implementation patterns, and verification guidance remain mandatory.

The floor applies only to AI Layer's managed bundled catalog. It does not reject user-authored or imported skills merely because they are shorter.

## Corpus policy

Shared structure is intentional because weak models benefit from predictable navigation. Shared prose is not. Each skill must contain subject-specific decision logic and verification relevant to its domain or stack.

Cross-cutting concepts may repeat where they are genuinely required (for example idempotency in webhooks and external integrations), but a skill must not be a renamed copy of another skill. Closely related frameworks may share architectural concepts while still providing framework-specific lifecycle, API, testing, deployment, and failure guidance.

The quality floor protects against regression; it does not encourage padding. Content that exists only to satisfy character or word thresholds violates the intent of this decision even if the gate cannot detect it mechanically.

## Consequences

- The bundled catalog and release wheel are larger on disk.
- Prompt cost remains bounded because native descriptors and core entry sections stay compact and deep content is retrieved on demand.
- Adding or materially reducing a bundled skill now requires enough domain content to pass the floor.
- Generic templating across skills becomes visible to CI through distinctiveness checks.
- Governance baseline must be intentionally refreshed when this gate changes because `scripts/skill_gate.py` is governance-sensitive.

## Verification

The change is accepted only when:

- the complete 43-skill catalog passes `scripts/skill_gate.py`;
- tests prove that the shipped catalog passes, a shallow bundled skill fails, and a near-duplicate bundled skill fails;
- existing native skill tests continue to prove compact descriptors and section-targeted loading;
- deterministic release wheel and release manifest are refreshed;
- canonical `make quality` passes in CI;
- the change is reviewed through a pull request before reaching `main`.

## Alternatives considered

### Keep quality editorial-only

Rejected. The repository already treats bundled skills as production agent infrastructure, and an unenforced convention can regress without a visible failure.

### Enforce only file size

Rejected. Size alone is easy to satisfy with padding and does not guarantee useful retrieval structure or distinct domain content.

### Put all deep guidance in descriptors

Rejected. That would defeat the native-first context economy. Descriptors should remain compact discovery surfaces; authoritative detail belongs in selectively retrievable skill sections.

### Apply the same floor to imported/user skills

Rejected. The repository controls the quality of its bundled catalog but should not prevent users from maintaining intentionally narrow local skills.
