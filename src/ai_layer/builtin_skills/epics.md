---
slug: epics
description: Epic-scale delivery discipline for decomposition, architecture gates, dependency order, task contracts, integration reviews and human acceptance.
kind: core
keywords:
- epic
- planning
- task decomposition
- orchestration
- acceptance
- architecture review
- integration
- milestone
- dependencies
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Epic Planning and Execution Skill

## Apply when

Use when work is too large or risky for one bounded task: multiple capabilities, architectural decisions, migrations, coordinated frontend/backend work, staged rollout or several independently reviewable changes. The purpose is to keep a large outcome coherent without turning the epic into one giant implementation context.

## Core contract

- An epic is an outcome with explicit scope, acceptance and integration logic—not a bucket of vaguely related tasks.

- Begin with Phase 0 reality audit: verify current code, architecture, constraints and already-implemented behavior before designing the target.

- Resolve architectural forks before parallel implementation. If two tasks depend on contradictory ownership/contracts, decomposition does not make the ambiguity disappear.

- Decompose by independently verifiable behavior and dependency boundaries, not by arbitrary file/component count.

- Every task needs a clear input context, owned scope, acceptance criteria, allowed dependencies, verification and handoff artifacts.

- Order tasks by enabling contracts/migrations first, implementations next, integration/hardening after; avoid parallel work on unstable shared contracts.

- Keep one source of truth for epic state and task status. Agents must not infer progress from prose or duplicate plan documents.

- Require independent review for material tasks and an integration review for the assembled epic; task-local green does not prove end-to-end coherence.

- A failed/changed task should update downstream assumptions explicitly rather than letting stale plans continue.

- Human acceptance is a separate gate from technical completion when the epic changes product behavior, architecture or other user-owned decisions.

## Evidence to inspect

- Current repository architecture, tests, migrations, configuration and recent code around the epic scope.

- Product/problem statement and non-goals, plus measurable/user-observable acceptance criteria.

- Known dependencies: data/schema, APIs, shared components, deployment, external services and organizational approvals.

- Risk register including security, compatibility, data migration, performance and rollback concerns.

- Existing task/epic mechanism in AI Layer and its authoritative state transitions.

- Integration/environment constraints needed to verify the complete outcome.

## Decision rules

- If a task cannot be reviewed/tested independently, either shrink it around one behavior or admit that the boundary is artificial and merge it with its owner work.

- If several tasks need the same new contract, define/approve that contract in an enabling task before parallel consumers implement against guesses.

- If a migration has mixed-version constraints, schedule expansion before code that depends on it and contraction after all old use is gone.

- If an architectural fork would change multiple downstream tasks, stop and resolve it before implementation rather than allowing agents to choose locally.

- If a task has broad allowed scope or vague “refactor as needed”, tighten ownership or split prerequisite cleanup.

- If late discovery invalidates acceptance criteria, revise the epic plan transparently; do not force implementation to satisfy obsolete wording.

- If individual tasks pass but integration behavior differs, integration findings take precedence and create explicit remediation tasks.

- If the epic cannot define a rollback/recovery path for high-risk rollout, it is not ready for execution.

## Workflow

1. Phase 0 — audit reality: map current flows, architecture, data, tests, known defects and constraints relevant to the outcome.

2. Define target outcome, non-goals, acceptance criteria, quality attributes and human decisions that require approval.

3. Identify architectural choices and produce a dependency/risk map. Resolve high-impact forks before task creation.

4. Create a task DAG with enabling contracts/migrations first, feature slices next, then integration/hardening/documentation as needed.

5. For each task, specify intent, scope/allowed paths or ownership, dependencies, acceptance, verification, risks and expected handoff.

6. Execute ready tasks through implement → targeted tests → canonical gates → independent review → remediation/re-review.

7. After each task, update authoritative epic state and downstream context if contracts/assumptions changed.

8. Run integration review across complete user journeys, shared contracts, migration/deployment and nonfunctional requirements.

9. Run final canonical quality/release gates and resolve all blocking findings.

10. Present the completed epic plus evidence/residual risks for human acceptance; archive only after acceptance policy is satisfied.

## Implementation patterns

- Vertical slice tasks are strong when they deliver a bounded observable capability across layers without forcing several teams/tasks to modify the same core files concurrently.

- Enabling tasks are appropriate for a stable shared contract, migration expansion or infrastructure seam that multiple later slices truly need.

- A task DAG is preferable to a flat checklist: dependencies should explain why a task is blocked and what artifact/contract it consumes.

- Use explicit integration tasks for cross-cutting behavior that cannot be proven inside one slice, such as end-to-end migration, performance, security or multi-provider switching.

- Keep research/spike tasks time- and output-bounded: their deliverable is a decision/evidence, not unreviewed production code.

- Remediation findings should be attached to the task/epic whose acceptance they block; avoid an unowned backlog of review comments.

- For parallel agents, minimize overlapping write ownership and stabilize shared interfaces first.

- Track decisions separately from transient implementation notes so handoffs remain compact and durable.

## Task quality contract

- A task title should name the behavior/outcome, not 'update files' or a layer name.

- Acceptance criteria must be externally or programmatically checkable; avoid 'clean', 'robust' or 'properly' without defining evidence.

- Dependencies must identify the exact prerequisite artifact/contract/state rather than simply another task ID.

- Verification must include the narrow checks for the task and the repository's canonical gates required at that stage.

- Handoff should record changed contracts, migration/feature-flag state, residual risk and what the next task can safely assume.

- Tasks should not secretly own architectural decisions already meant to be settled at epic level.

## Review and remediation

- Independent review examines correctness against task acceptance plus architecture/security/data/compatibility risks, not formatting preference.

- A passing review cannot contain unresolved actionable findings; medium/high findings require remediation or explicit accepted-risk decision.

- After remediation, re-review the changed area and any contract invalidated by the fix rather than assuming comments were resolved.

- Integration review intentionally ignores task boundaries and traces complete journeys, shared data and deployment behavior.

- Critical changes may require stronger reviewer/model/human approval according to project governance.

## Progress and handoff

- Status must come from authoritative task/epic state, not a narrative summary that can drift.

- When a task discovers new scope, record whether it is required for current acceptance, a dependency defect or separate follow-up.

- Do not keep huge transcripts as epic memory. Preserve decisions, contracts, evidence and unresolved risks only.

- At each handoff, state the next ready task and why it is ready, or the exact blocker/decision needed.

## Failure modes

- Mega-task epic: one task contains most implementation and defeats independent review/context control. Decompose by behavior/dependency.

- Layer decomposition only: separate backend/frontend/database tasks all guess shared semantics. Stabilize contract and prefer slices where possible.

- Parallel contract drift: agents implement different assumptions simultaneously. Resolve shared contract first.

- Status theater: plan says complete while repository/task state differs. Use authoritative state and executable evidence.

- Review flag only: same implementation context self-approves. Require independent reviewer where governance calls for it.

- Task green/integration broken: local tests pass but journeys/rollout fail. Add integration review/gates.

- Architecture decision hidden in implementation: downstream tasks become inconsistent. Promote the decision and replan.

- Permanent transition tasks: flags/shims/migration compatibility never contract. Include explicit cleanup condition and later task.

- Unbounded discovery: epic planning keeps expanding before any outcome can ship. Separate non-goals/follow-ups and preserve release slices.

- Human gate bypass: technical green is treated as product acceptance. Keep acceptance stage explicit.

## Verification

- Confirm every acceptance criterion maps to one or more tasks and final integration evidence.

- Validate task DAG has no circular or missing dependency and shared contracts are defined before consumers.

- Check no two parallel tasks require uncontrolled edits to the same authoritative subsystem without coordination.

- Run per-task targeted/canonical gates and independent reviews according to project governance.

- At integration, trace complete success plus material failure/rollback journeys across task boundaries.

- Verify migrations/feature flags/compatibility transitions are in the expected phase and cleanup is scheduled/completed.

- Run final canonical quality/release suite against assembled branch.

- Compare final diff to epic non-goals/scope for accidental expansion.

- Summarize residual risk and unexecuted verification before human acceptance.

- Archive tasks/epic only when authoritative status and acceptance policy permit.

## Completion criteria

- The intended product/engineering outcome is demonstrably satisfied, not merely all tasks marked done.

- Architecture decisions and shared contracts are coherent across all task implementations.

- Task reviews/remediations and final integration review have no unresolved blocking findings.

- Migration/compatibility/feature-flag lifecycle is safe and not left in an accidental transitional state.

- Canonical quality/release gates pass for the assembled result.

- Human acceptance is recorded where required, with residual risks explicit.

- The epic leaves a clean authoritative history of decisions, evidence and follow-up rather than a giant transcript.

## Related skills and escalation

- Use `architecture` during Phase 0/architecture gates and `legacy-change` when the epic modifies poorly understood systems.

- Use specialized skills (`database-migrations`, `security`, `design`, etc.) inside tasks that carry those risks.

- Use `verification` to make final acceptance evidence explicit.

- Escalate unresolved architecture/product forks to the human owner before allowing dependent tasks to implement conflicting guesses.
