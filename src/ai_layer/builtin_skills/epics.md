---
slug: epics
description: Live AI Layer Epic lifecycle for versioned specifications, independent audit, Phase 0, ordered managed Tasks, drift review, closure evidence and archive.
kind: core
keywords:
- epic
- planning
- task decomposition
- orchestration
- acceptance
- architecture review
- integration
- phase 0
- epic_next
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# AI Layer Epic Lifecycle Skill

## Apply when

Use when the user is designing, approving, resuming, executing, reconciling or closing an AI Layer Epic. An Epic is durable product/architecture specification and scheduling state over the existing managed Task engine. It is not a second implementation runtime and it is not a generic task-DAG framework.

If an Epic already exists, especially one created by an older AI Layer release, **do not infer its next procedure from this skill, chat history or stored prose**. Call `project_status`, identify the active/selected Epic, then call `epic_next`. The live `epic_next` response plus its current `agent_contract`/Project Map contract defines present runtime procedure.

## Core contract

- Current repository source is authoritative for code truth. Epic specifications express intended outcome, not proof of current implementation.

- `epic_next` is the authoritative live Epic navigator. Use it after Epic transitions, linked Task completion, context loss and when resuming an executing Epic.

- The current AI Layer runtime contract overrides historical Epic wording about procedure. Older specs remain valid product history but do not freeze old tool semantics.

- DRAFT and APPROVED Epics are passive. They do not reserve ordinary host-native work or require unrelated work to enter a managed Task.

- An Epic specification is immutable by version. Normal edits create a new version; human approval applies to one exact current version.

- Independent specification audit is an Epic operation, not managed Task DISCOVERY. Use `epic_audit_prepare` and `epic_audit_record`; do not fabricate an audit or route it through `task_stage_delegate`.

- Phase 0 is source-authoritative reconciliation before implementation planning. AI Layer executes it as an ordinary read-only `ANALYSIS_ONLY` managed Task.

- After successful Phase 0, the execution plan is an **ordered sequential list** of implementation work items. AI Layer owns conversion to managed Tasks and appends the mandatory final whole-Epic closure/review Task.

- Each linked implementation/final Task uses the current managed Task engine and its strict stage contracts. Do not reproduce IMPLEMENT/REVIEW/FIX logic inside the Epic layer.

- Repository drift and accepted standalone Tasks are explicit boundaries. Follow `epic_next`: narrow intervening impact review is preferred when sufficient; targeted reconciliation is used when assumptions may actually have changed.

- Final Epic closure requires real evidence from the final managed Task: documentation updated where required, reviewed Project Knowledge published, and scoped `ProjectMapReconciled` evidence.

- Project Map is navigation metadata, not Project Knowledge. Read it with `project_search`; update it with `project_map_reconcile` only for current-source scope actually inspected/understood.

## Workflow

Use the live state machine rather than reconstructing a workflow from memory:

1. Start with `project_status` and identify whether the Epic is current focus or explicitly selected by the user.
2. Call `epic_next` and follow exactly the returned action for the current Epic state.
3. While DRAFT, refine the versioned specification and run independent spec audit when appropriate; obtain explicit human approval for the exact current version.
4. When directed, run Phase 0 as the returned read-only `ANALYSIS_ONLY` managed Task. Follow `task_next` until that Task completes, then record reconciliation through the Epic tool returned by `epic_next`.
5. After successful Phase 0, submit only ordered implementation work items. AI Layer owns the mandatory final closure item.
6. For each started plan item, switch authority to its managed Task and follow `task_next` through IMPLEMENT/REVIEW/FIX/verification. Return to `epic_next` after terminal Task success.
7. If the Epic reports intervening accepted work or unattributed repository drift, perform only the returned narrow impact review/reconciliation rather than inventing a broader audit.
8. During final closure, satisfy the returned documentation, reviewed Project Knowledge and scoped Project Map evidence requirements. If only Project Map evidence is missing, reconcile against the already-completed final Task rather than creating another implementation Task.
9. Archive only when `epic_next` returns the archive action.

Every transition must come from the live runtime. Stored Epic prose describes intended product outcome/history; it does not override current tool semantics.

## Authoritative tools

- `epic_create` — create DRAFT spec v1 after the outcome is understood.
- `epic_spec_get` — fetch exact current/older specification text.
- `epic_spec_edit` — preferred atomic document-like edits before Phase 0.
- `epic_spec_revise` — full-spec replacement fallback before Phase 0.
- `epic_audit_prepare` / `epic_audit_record` — independent pre-Phase0 specification review.
- `epic_approve` — explicit human approval of the exact current specification version.
- `epic_next` — authoritative live navigator for all states.
- `epic_start_next` — start exactly the next eligible Phase0/drift/plan Task only when `epic_next` directs it.
- `epic_reconcile_complete` — record Phase0/drift reconciliation after the linked analysis-only Task completed.
- `epic_plan_set` — submit implementation work items after successful Phase 0; AI Layer adds final closure automatically.
- `epic_intervening_review_prepare` / `epic_intervening_review_record` — assess accepted standalone work since the Epic boundary.
- `project_map_reconcile` — record scoped Project Map evidence when final closure requests it.
- `epic_archive` — archive only after `epic_next` says archive.

## Decision rules

- If `project_status` reports an executing Epic and the user says “continue”, call `epic_next` instead of reconstructing state from documentation or repository history.

- If the Epic is DRAFT, refine/audit the product specification. Do not create implementation Tasks merely because a task list seems obvious.

- If the current specification changed after approval, treat the new version as requiring current approval/audit state according to the returned Epic contract; never transfer approval by assumption.

- If `epic_next` requests Phase 0, start only the returned analysis-only Task and follow `task_next` for that managed Task.

- If Phase 0 finds an obvious non-branching correction, reconcile it into the execution specification. If it finds a genuine material product/architecture trade-off, surface that decision to the human instead of letting a worker choose silently.

- If `epic_next` says `create_task_plan`, plan only implementation work items. Do not manually add another Phase 0 or final closure item; AI Layer owns those boundaries.

- Do not invent parallel execution. The current Epic plan executes in ordered sequence through the managed Task engine unless the live runtime explicitly gains another contract in a future version.

- If an unrelated accepted Task occurred during Epic execution, use the intervening review flow returned by `epic_next`; do not automatically perform a full repository audit.

- If repository drift is detected outside safely attributable accepted Task boundaries, follow targeted drift reconciliation. Never reset/stash/discard user changes just to restore an Epic digest.

- If final docs and Project Knowledge evidence are complete but Project Map evidence is missing, do **not** create another final implementation Task. `epic_next` returns `project_map_reconcile` with the already-completed final Task key. Reconcile checked scope (or honest `no_changes_reason`), then call `epic_next` again.

- Archive only when `epic_next` returns archive. “All implementation tasks look done” is not sufficient closure evidence.

## Evidence to inspect

Use evidence proportionally to the current Epic state. Do not turn every Epic transition into a repository-wide audit.

For specification/Phase 0 work, inspect current source paths that implement the intended behavior, relevant tests, schemas/migrations, configuration, integration boundaries, deployment/runtime constraints, and existing Project Knowledge/Decisions only when they materially affect the outcome. Use `project_search` to reduce discovery breadth when the location is unknown, then open current source before making code-truth claims.

For implementation items, evidence comes from the linked managed Task: its actual repository delta, verification commands/results, worker provenance, review findings and remediation history. Do not substitute Epic summaries for Task evidence.

For drift/intervening review, inspect only the accepted changed paths and the remaining Epic assumptions they could invalidate. For final closure, inspect the assembled cross-task result, required documentation changes, reviewed Knowledge publication evidence, and `ProjectMapReconciled` scope attached to the final Task.

Historical Epic specs, sessions and documentation are useful rationale/context but cannot prove current code behavior. Scanner/Project Map metadata can guide navigation but is not source truth.

## Phase 0 reality audit

Phase 0 answers whether the approved intended outcome still matches current source before implementation planning begins.

Inspect only evidence relevant to the Epic: current flows, architecture boundaries, data/schema, integrations, tests, deployment constraints, known defects and already-implemented behavior. Project Map can reduce discovery breadth, but current files remain authority.

The deliverable is a compact reconciliation result: confirmed assumptions, factual corrections, risks, and only genuine human decisions. Do not turn Phase 0 into an unbounded architecture rewrite or general repository audit.

The Phase 0 Task is read-only `ANALYSIS_ONLY`. Its worker follows the managed Task delegation contract returned by `task_next`; the Epic coordinator does not edit source during that stage.

## Implementation patterns

Plan and execute Epics as ordered outcome slices through the existing managed Task engine. Prefer each implementation item to produce one independently verifiable coherent result rather than one task per file/layer.

Stabilize true contracts before consumers when required: schema/API/interface seams first, behavior slices next, integration/hardening where the Epic acceptance criteria need them. Avoid speculative infrastructure, parallel abstractions, and vague “refactor as needed” items.

Inside each item, let the managed Task engine own IMPLEMENT/REVIEW/FIX/verification and worker boundaries. The Epic layer schedules and reconciles; it does not duplicate repository mutation, worker leases, findings, checks or review state.

Treat Phase 0, intervening review, drift reconciliation and final closure as explicit boundaries rather than ordinary implementation items. Project Knowledge publication and Project Map reconciliation use their own supported evidence contracts; neither should be fabricated to make an Epic mechanically green.

## Planning contract

After Phase 0, create implementation work items that are independently verifiable and small enough for the managed Task lifecycle. Each item should name an outcome, not merely a file/layer.

Prefer dependency order that stabilizes contracts before consumers: migrations/contract seams first when truly required, behavior slices next, integration/hardening where the outcome needs it. Avoid vague “refactor as needed” scope.

The plan is ordered, not a generic graph. Do not launch several plan items concurrently because an older planning skill or stored Epic prose mentions a DAG. The live runtime owns scheduling.

The mandatory final Task is automatically appended by AI Layer. It is responsible for whole-Epic integration/closure evidence, including appropriate docs, reviewed durable Project Knowledge and Project Map reconciliation.

## Managed Task execution inside an Epic

Once an Epic plan item is started, the linked Task becomes the authoritative execution unit. Call `task_next` and follow its exact stage contract.

- IMPLEMENT/FIX stages are writable delegated workers (or current MICRO inline behavior when the Task engine explicitly returns it).
- DISCOVERY/REVIEW stages are read-only delegated workers.
- REVIEW findings must be resolved/re-reviewed according to Task state; Epic state does not bypass Task gates.
- Only actual verification/review evidence may be recorded.
- The Epic coordinator must not claim worker work or duplicate stage execution itself.

After a linked Task reaches terminal success, return to `epic_next`. Do not infer the next plan item from a saved list because drift/intervening-review/closure state may have changed.

## Project Knowledge and Project Map closure

Project Knowledge and Project Map have different purposes and different write semantics.

**Project Knowledge** stores reviewed durable facts/invariants/fragile-area knowledge. Authoring/publishing is review-gated through supported managed Task flow. Ordinary unmanaged host-native work may read it with `knowledge_search` but must not pretend it can directly publish VERIFIED knowledge.

**Project Map** answers where code lives and how inspected areas relate. Structural facts are scanner-owned. Semantic enrichment is agent-authored only from current-source evidence via `project_map_reconcile`.

For final Epic closure, `ProjectMapReconciled` must be tied to the completed final Task and non-empty checked `scope_paths`. If the existing map is already accurate, use `no_changes_reason`; never manufacture descriptions just to satisfy the gate.

## Drift and intervening work

An Epic repository digest is a durable boundary, not permission to rewrite user Git state.

When accepted standalone managed Tasks occurred since the Epic boundary, AI Layer can ask for a narrow read-only impact review. Judge only whether those changes invalidate remaining Epic assumptions. Record `unaffected` when they do not; route to reconciliation only when they do.

For unattributed repository drift, run the targeted analysis-only reconciliation returned by `epic_next`. Resolve clear factual drift automatically. Ask the human only when multiple materially different acceptable outcomes exist.

Never stash, reset, restore, discard or commit changes merely to make an Epic digest match.

## Verification

Per-item verification lives in the managed Task engine. Use the Task’s narrow checks, canonical gates and independent REVIEW/FIX cycles as returned by `task_next`. Record only checks that actually ran and worker/reviewer evidence that actually exists.

The final Task must evaluate the assembled Epic, not just repeat the last item’s local tests. Verify cross-task contracts, integration paths, migrations/deployment implications and user-observable acceptance criteria that the Epic actually owns. Where the Epic changes persistence/public interfaces/deployment/security, include the relevant stronger checks required by those domains.

Closure evidence is mechanical and separate from implementation confidence: required documentation must be current, durable Project Knowledge must have passed its supported review/publish flow, and Project Map reconciliation must be scoped to the completed final Task. An honest `no_changes_reason` is valid map evidence when checked semantics were already accurate.

A passing final Task plus closure artifacts still does not authorize archive by inference. Return to `epic_next`; its mechanical closure state is authoritative.

## Failure modes

- **Old-spec procedure drift:** following stored Epic text that predates current tools. Fix: call `epic_next`; live runtime contract wins.
- **Generic DAG orchestration:** parallelizing plan items because generic planning advice says so. Fix: current AI Layer Epic execution is ordered/sequential.
- **Phase 0 bypass:** planning implementation before source reality is reconciled. Fix: complete the returned analysis-only Phase 0 Task.
- **Epic self-implementation:** coordinator edits source while a linked managed Task owns execution. Fix: follow `task_next` delegation boundaries.
- **Full drift audit by default:** rescanning the repository after unrelated accepted work. Fix: use narrow intervening review first when returned.
- **Map/Knowledge conflation:** storing navigation prose as VERIFIED Project Knowledge or treating scanner evidence as semantic truth. Keep surfaces separate.
- **Fake closure content:** inventing Knowledge or Project Map text solely to pass a gate. Record only source-backed durable knowledge; use honest Project Map no-change reconciliation where applicable.
- **Redundant final retry:** creating a second final Task when only Project Map evidence is missing. Use the completed final Task key with `project_map_reconcile`.
- **Archive by chat memory:** assuming completion because all visible tasks look green. Archive only when `epic_next` says archive.

## Completion criteria

- Current approved Epic outcome is reconciled with current source through Phase 0.
- Ordered implementation items completed through their actual managed Task contracts.
- Any intervening work/drift was reviewed or reconciled through the returned Epic flow.
- Final whole-Epic Task passed its real verification and independent review requirements.
- Required documentation is current.
- Durable Project Knowledge produced by the final work is reviewed/published where applicable.
- Scoped Project Map reconciliation evidence exists for the final Task, including honest no-change evidence when appropriate.
- `epic_next` returns archive and `epic_archive` succeeds.
- Residual risks/follow-ups are explicit and are not disguised as completed acceptance.

## Related skills and escalation

Use `ai-layer-workflow` for the overall control-plane boundary, `architecture` during material Phase 0 architecture analysis, `legacy-change` when current behavior is poorly understood, and domain skills such as `database-migrations`, `security`, `design` or `verification` inside the managed Tasks that need them.

Escalate only genuine human-owned product/architecture trade-offs or explicit high-impact authorization gates. Do not escalate ordinary state-machine navigation that `epic_next` can resolve deterministically.
