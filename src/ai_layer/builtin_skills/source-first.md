---
slug: source-first
description: Source-first engineering discipline that treats executable code and observable
  behavior as authority over prose claims.
kind: core
keywords:
- source
- code
- behavior
- evidence
- repository
- contract
entry_sections:
- Apply when
- Core contract
---
# Source First Skill

## Apply when
Every engineering task that reads, changes, reviews, or diagnoses an existing repository.

## Core contract
- Treat current source code, executable contracts, migrations, tests, and reproduced behavior as primary evidence.
- Documentation, comments, changelogs, prompts, and historical explanations are hypotheses until confirmed by source or execution.
- Read the owning module and affected callers before editing; do not reconstruct behavior from names alone.
- Distinguish tests that prove observable behavior from tests that only freeze an implementation detail.
- When evidence conflicts, report the conflict and follow the strongest reproducible source rather than silently choosing prose.

## Verification guidance
State which source paths and executable checks support each important conclusion. Mark unavailable runtime evidence as unavailable.

## Failure modes
Trusting README claims over code, assuming a test covers a behavior it never exercises, copying historical architecture without inspecting current ownership, and presenting inferred behavior as verified.
