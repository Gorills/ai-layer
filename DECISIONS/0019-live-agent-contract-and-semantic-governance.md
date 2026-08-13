# ADR 0019 — Live agent contract and semantic governance

## Status

Accepted for 0.13.3.

## Context

AI Layer moved from a mandatory memory/task permission layer to a Project Intelligence control plane in 0.13.x. The runtime behavior changed correctly, but several old assumptions remained in bootstrap prose, MCP descriptions, skills, internal QA/smoke flows and tests. Some tests also encoded incidental implementation details such as exact bootstrap byte size, exact builtin-skill count, exact static-policy rule count, or historical tool names.

Those checks can become architecture by accident: a useful instruction may be shortened only to satisfy a byte ceiling, adding a valid skill may fail CI because the catalog count changed, or a correct `project_status`-first flow may be rejected because old QA still requires `memory_context`.

Weak coding agents need complete, current and internally consistent operating instructions more than they need arbitrary reductions in a small always-on bootstrap. At the same time, unbounded or duplicated agent-facing material is still undesirable.

## Decision

AI Layer uses one current, versioned agent runtime contract as the procedural authority for agent-facing behavior.

- `project_status` is the current registered-project state/bootstrap surface.
- Project Map, Knowledge, Decisions, Skills, Tasks and Epics expose focused current capabilities through their canonical tools.
- Historical Task/Epic prose and legacy compatibility tools cannot override the current runtime/tool contract.
- `memory_context` and `memory_search` remain explicit compatibility surfaces only; current internal/application naming uses Project Intelligence terminology.
- Current QA/smoke flows validate the current control plane. Legacy flows may remain readable for migration/telemetry, but must be labeled as legacy and must not define current success criteria.
- Integration/bootstrap compatibility versions have one production source of truth.

Tests and governance protect semantic/product contracts rather than incidental representation whenever possible. Therefore:

- do not impose bootstrap byte ceilings merely to reduce context; test that always-needed instructions are complete, non-duplicated and current;
- do not assert an exact builtin-skill count when the real requirement is a valid routable catalog and required core capabilities;
- do not assert an exact number of policy rules when the real requirement is the presence and uniqueness of required engineering invariants;
- do not use transitive dependency counts as release correctness evidence when closed-world lock verification already checks the actual package set;
- do not assert exact prose when a structured field or semantic invariant can prove the contract;
- meaningful bounded payload limits must be named production constants/contracts rather than unexplained magic numbers copied into tests.

Hard limits remain appropriate when they represent a real external, safety, performance or protocol boundary, such as schema identifier length, embedding dimensions, bounded query/result limits, privacy limits, retry/remediation ceilings, or supported runtime/platform constraints.

## Consequences

- Bootstrap may grow modestly when additional always-needed guidance is required; correctness and weak-model comprehension take priority over arbitrary byte targets.
- Specialized Task/Epic/domain procedure remains progressive so the always-on contract does not become a full manual.
- CI is less likely to force the product back toward historical architecture after a refactor.
- Compatibility code is easier to identify because legacy naming is explicit rather than silently reused as the current internal abstraction.
- Future changes to agent-facing behavior require updating the canonical runtime contract and semantic regression tests rather than chasing duplicated prose and magic thresholds.
