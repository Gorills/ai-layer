---
slug: epics
description: "Durable Epic specs, audits, Phase 0 reconciliation, sequential reviewed Tasks, drift recovery, final review and knowledge closure."
kind: core
keywords:
- epic
- epics
- specification
- spec
- architecture plan
- roadmap feature
- phase 0
- final review
- create epic
- approve epic
- audit epic
- эпик
- спека
- спецификац
- согласовано
- аудит эпика
- фаза 0
---
# Epics Skill

## Apply when
The user wants to turn a settled multi-task product/architecture decision into a durable Epic, audit or revise an existing Epic, approve it, execute it end-to-end, recover its state, or perform the mandatory final whole-Epic review.

## Core model
An Epic is an approved contract for a final usable product outcome plus a scheduler over ordinary Task Engine Tasks. It is not a second Task Engine. Epic state owns specification versions, audits, approval, Phase 0 reconciliation, plan ordering, progress aggregation, drift reconciliation and final closure. Every implementation/fix/review mutation still belongs to the existing Task Engine.

## Mandatory navigation rule
- Never infer Epic state or the next step from chat history.
- Read the durable Epic with `epic_get`, then call `epic_next` after every Epic transition, after every linked Task transition/completion, and after context loss.
- Invoke the tool named by `epic_next`. While it returns `continue_task`, switch to `task_next` until that linked Task reaches a terminal state, then immediately return to `epic_next`.
- Reuse the canonical `project_root`. If an Epic/Task tool fails, correct the state/input or report the blocker; never silently bypass the layer.

## Creating a complete Epic
When the user says the solution is understood and asks to create an Epic:
1. Convert the actually accepted discussion decisions into one complete human-readable Markdown specification and call `epic_create`.
2. The specification describes the final usable selected-scope product, not a tentative implementation plan and not a list of Tasks.
3. Include at minimum: Goal, Product Outcome, current problem/context, Accepted Decisions, Functional Requirements, architecture/contracts/data/UX/operations as relevant, edge cases, compatibility/migrations/security/privacy as relevant, explicit non-goals, Acceptance Criteria, and Definition of Done.
4. MVP may reduce scope only. Inside the selected scope, do not intentionally choose temporary, placeholder, partial, trial, knowingly incomplete, or later-to-be-replaced architecture merely to ship sooner.
5. Preserve genuine unknowns explicitly. Do not invent decisions that the user never accepted.

## Audit and revision before execution
- Audit rounds are unlimited before Phase 0, including after approval but before execution starts.
- For an independent audit, first read the current exact spec with `epic_get`; inspect source when the audit claim depends on current code. Do not treat prior audit conclusions as authority when independence was requested.
- Record the actual audit with `epic_audit_record`. Findings should state the concrete gap/risk and the required correction or decision.
- If the audit/discussion changes the spec, call `epic_spec_revise` with the complete new spec. Never silently rewrite an older version. Revising an already-approved-but-not-started Epic returns it to DRAFT and requires explicit reapproval.
- Do not call `epic_approve` until the user explicitly communicates approval/agreement of the current spec (for example “согласовано”, “approved”, “берём так”).

## Approval boundary
Approval freezes the human baseline `approved_spec_version`. Later automatic Phase 0 corrections create a newer execution version and must preserve the approved historical version and rationale. Approval does not authorize implementation before Phase 0.

## Mandatory Phase 0
The first execution Task is always Phase 0 and is read-only analysis.
- Start it only when `epic_next` says `start_phase0`.
- The Phase 0 worker must call `epic_get` and compare every material spec assumption with current source.
- Check for stale facts, existing extension points, incompatible contracts, missing constraints, silent scope loss, and temporary/incomplete selected-scope solutions.
- Source is authoritative over Project Knowledge/history.
- Non-branching correction: apply automatically in `epic_reconcile_complete`.
- Several options but one clearly superior durable recommendation: choose it automatically, record rationale, update the execution spec.
- Genuine material product/architecture trade-off: put it in `human_decisions`; this intentionally blocks the Epic for the user. After the user chooses, call `epic_reconcile_complete` again with the resolved execution spec and an empty `human_decisions` list so Phase 0/drift continues from the same durable reconciliation context.
- Do not create implementation Tasks before Phase 0 reconciliation succeeds.

## Planning after Phase 0
When `epic_next` requests `epic_plan_set`, derive implementation work items only from the reconciled execution spec.
- Each item must be independently understandable: goal, concrete acceptance criteria, constraints.
- Every implementation item is STANDARD/review-gated. Do not downgrade Epic work to MICRO.
- AI Layer adds the completed Phase 0 item and mandatory final closure/full-review item automatically.
- Prefer coherent vertical/ownership boundaries over arbitrary equal-sized chunks.

## Continuous execution
For “do the whole Epic” / continuous execution:
1. Call `epic_next`.
2. If it says `epic_start_next`, start exactly that one eligible linked Task.
3. Run the linked Task entirely through `task_next` and its normal delegation/IMPLEMENT/REVIEW/FIX rules.
4. When the Task is terminal, call `epic_next` again immediately.
5. Continue sequentially until final review passes and `epic_next` says archive.
Never run Epic Tasks in parallel; one project still has one open Task/stage/worker at a time.

## Drift detection
AI Layer records the repository identity observed by the accepted terminal Task stage. If repository state changes outside that verified boundary before the next item, `epic_next` requires a targeted analysis-only drift reconciliation.
- Reconcile only affected remaining assumptions/plan items.
- Apply obvious/strong-recommendation corrections automatically.
- Escalate only genuine material trade-offs.
- Never ignore drift and continue from a stale plan.

## Mandatory final Task
The last successfully completed Epic Task is always the final closure/full-Epic review Task.
- IMPLEMENT updates relevant project documentation and `CURRENT_STATE.md` and drafts durable Project Knowledge from current source evidence.
- REVIEW is independent/read-only and reviews the whole implemented Epic against the current execution spec and Definition of Done, not only the documentation delta of the final Task.
- It must inspect DRAFT Project Knowledge before PASS so the existing Task Engine can publish it only after independent review.
- Review integration across all prior Tasks, regressions, migrations/compatibility, security/privacy, operational behavior, edge cases, dead code, TODOs/stubs, and incomplete/temporary selected-scope solutions.
- Findings use the existing FIX -> REVIEW remediation loop. Never archive an Epic with open findings.
- Mechanical closure requires documentation changes and at least one reviewed Project Knowledge publication. If either is missing, AI Layer schedules another final-review attempt automatically.

## Completion and archive
Call `epic_archive` only when `epic_next` explicitly says archive. Archive preserves all spec versions, audits, Phase 0 evidence, plan/Task links, final review history and closure evidence. Project Knowledge stores current durable facts, not the full Epic execution diary.

## Failure modes
Creating Tasks before approval/Phase 0; treating MVP as permission for temporary architecture; silently editing an approved spec; relying on stale chat context; skipping independent audits; running Epic Tasks in parallel; allowing the orchestrator to implement instead of Task workers; final review limited to the last delta; closing without documentation/knowledge reconciliation; ignoring repository drift.
