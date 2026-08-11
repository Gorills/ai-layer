---
slug: legacy-change
description: Evidence-first modification discipline for unfamiliar or fragile existing
  code, automatically activated by scanner fragility signals.
kind: capability
keywords:
- legacy
- refactor
- characterization
- old code
- unfamiliar
- regression
- compatibility
- fragile
- existing old code
- unfamiliar code
- refactor legacy
- preserve behavior
- brittle
- легаси
- старый код
- рефакторинг старого
entry_sections:
- Apply when
- Core contract
---
# Legacy Change Skill

## Apply when
Scanner evidence indicates meaningful change fragility, or the task modifies unfamiliar/weakly tested/highly coupled code whose current externally observable behavior must be preserved.

## Core contract
- Treat current code, callers, tests, data contracts and reproduced runtime behavior as evidence. Comments/README intent never overrides actual behavior without verification.
- Before editing, identify the smallest ownership seam and the callers/data/side effects that cross it.
- Preserve observable quirks unless the task explicitly classifies them as defects. Do not “clean up” ambiguous behavior by taste.
- Prefer small reversible changes and characterization/regression tests over broad rewrites.
- Do not create a parallel architecture/flow to avoid understanding the existing one.
- Keep unrelated renames/formatting/cleanup out of behavioral changes so review can see cause and effect.

## Reconnaissance
Start from the task entry point, trace only relevant calls, persistence, side effects and integrations, then inspect nearby tests/history-like evidence available in the repository. Use project intelligence for runtime/data/test topology, but verify source before concluding. Do not scan/rewrite the entire repository when one path can establish the contract.

## Characterization
When behavior is weakly documented, capture the current observable behavior with focused tests or reproducible commands before changing it. Characterization is especially important for parsing, billing, state transitions, permissions, integrations and compatibility quirks.

## Refactoring
Extract behind an existing seam only when it reduces risk for the requested change now. Avoid architecture migrations disguised as cleanup. If a broader redesign is genuinely necessary, surface it as a consequential decision rather than silently expanding scope.

## Persistence and migrations
Assume existing production data can contain historical edge cases not represented by fixtures. Schema/data changes should tolerate current rows, be bounded for large datasets and preserve deployment compatibility where old/new code can overlap.

## External behavior
Trace API contracts, templates, cron/workers, webhooks and external side effects before changing signatures or ordering. A locally cleaner implementation is not an improvement if it breaks an undocumented but real caller.

## Stopping rule
If the current behavior cannot be determined safely from available evidence and the task would require guessing a consequential invariant, stop with a precise evidence gap instead of performing a speculative rewrite.

## Quality gate
Compare before/after behavior at the relevant boundary, add a regression for the motivating failure when deterministic, run the narrowest real integration that can falsify the change, and keep the final diff coherent/reviewable.
