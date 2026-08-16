# ADR 0025 — MCP response envelopes

## Status

Accepted for the current improvement program.

## Context

ADR 0019 made one versioned runtime contract the procedural authority and warned that duplicated agent-facing material is undesirable: completeness belongs in bootstrap, not every payload. The 0.14.x delivery already collapsed native bootstrap to one procedure copy and stopped reprinting `agent_contract` from `project_status`.

Navigators, search and knowledge still attached the same essays on every call: full `agent_contract` on `task_next`/`epic_next` (including idle), `query_contract`/`language_contract`/`source_contract` on search, Project Map capability text on every `epic_next`, idle `latest` Task dumps, and worker packets that mixed orchestrator protocol with the job. Weak agents re-read procedure instead of the live `next_action`. This is v3 *delivery* of the existing runtime contract, not a second constitution or workflow engine.

## Decision

One runtime contract remains the procedure source. Native bootstrap owns ordinary procedure once; MCP initialize instructions are the compact fallback when that bootstrap is missing. MCP payloads declare `envelope`: `ordinary` | `managed_next` | `worker`.

- **ordinary** — data only for `project_status`, `project_search`, `knowledge_search` and Work tools. No `agent_contract`, `query_contract`, `language_contract`, `source_contract`, Project Map capability essay, or `language_policy`.
- **managed_next** — live `next_action` plus current stage/Epic facts for the orchestrator. Attach `runtime_contract_version`. Do not reprint bootstrap or the full `agent_contract`. Live `next_action` remains authority over stored Task/Epic prose. A short stage-local `orchestrator_contract` may sit on `next_action` for the current stage (do not edit / start worker); do not also attach a duplicate top-level managed orchestrator essay.
- **worker** — job packet for a delegated subagent only (`goal`, acceptance criteria, constraints, role, `repository_mode`, findings, completion tool/required fields, `provenance_notice` if any, `project_knowledge_review` if DRAFT). The worker must not receive `orchestrator_contract` or protocol essays (`identity_enforcement`, `expertise_contract`, `check_evidence_assurance` text).

Full `agent_contract` is never attached on idle or ordinary polls. Prefer never attaching the full essay when `next_action` plus bootstrap already define procedure. `epic_next` attaches `project_map_capability_contract()` only when `next_action.tool == "project_map_reconcile"`; the function remains available for old-Epic/on-demand use. Idle `task_next`/`task_current` is compact `{active: false, envelope, next_action: host_native}` with no `latest` Task dump. `task_stage_delegate` returns `orchestrator` (tiny `next_action`) and `worker` (slim packet).

`knowledge_search` omits `evidence[]` hashes by default; keep `source_pointers` and `stale_reason`. Reviewers still use `knowledge_list`. Search still returns breadcrumbs (path, semantic, symbols, score, `queries_used`). `source_verification_required` may remain a boolean when freshness is not `fresh`/`refreshed`. The MCP tool catalog stays unfiltered. `project_root` echo, `project_policy`, `work.continuation`/`current_focus`, live vs status, and stale open Work remain.

Internal persistence/dashboard views may still store a full `delegation_contract`; MCP-facing Task/Epic responses must not dump those essays to agents.

## Consequences

- Ordinary and managed-poll context stays on state and the next tool, not a reprinted manual.
- Delegated workers receive a job, not orchestrator procedure.
- Old Epics still learn Project Map rules at reconciliation time without paying the essay on every `epic_next`.
- Runtime contract v3 is a delivery change; product release numbering is independent and this ADR does not claim an unshipped 0.15 release.
