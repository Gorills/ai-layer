# ADR 0016 — Epics v1 is a durable specification and scheduler over Task Engine

**Status:** accepted for Epics v1.

## Context

AI Layer already has a durable sequential Task Engine with worker provenance, read-only review/discovery, writable implement/fix stages, repository baselines, verification, findings and remediation. Large product/architecture changes need a higher-level object that can preserve a human-approved outcome across chats, survive audits and source drift, decompose into Tasks only after reality reconciliation, and prove the whole result is complete.

Creating another stage engine inside Epics would duplicate the strongest existing capability and create two sources of truth. Conversely, a plain checklist is insufficient: the approved specification, pre-execution reconciliation and final whole-product closure need durable state and explicit gates.

## Decision

### 1. Epic owns the product contract and scheduling intent

Epics own:

- immutable specification versions;
- unlimited pre-approval audit records bound to an exact spec version;
- an explicit human-approved specification baseline;
- a reconciled execution-spec version;
- Phase 0 result/corrections and unresolved human decisions;
- ordered plan items and their links to ordinary Tasks;
- repository-drift reconciliation between accepted Task boundaries;
- progress aggregation;
- whole-Epic completion/archive state.

Epic domain contracts remain under `ai_layer.epics`. Persistence and composition live outside that domain package. The application layer may invoke public Task services to create the one eligible Task, but Epic domain code must not import or duplicate Task internals.

### 2. Approval is a durable human boundary

`approved_spec_version` is immutable history. Later Phase 0 or drift corrections create a newer execution version with rationale; they never rewrite the version the human approved.

Only explicit user agreement may approve a DRAFT Epic. Audits and spec revisions before approval are unlimited.

### 3. Phase 0 is always the first execution Task

No implementation plan may be finalized before Phase 0. Phase 0 is an ordinary `analysis_only` Task, therefore it is technically read-only through the existing Task Engine.

Its contract is:

- current repository source is authoritative;
- verify material assumptions and accepted decisions against current code;
- detect stale facts, already-existing extension points, incompatible contracts and missing constraints;
- detect silent scope loss and temporary/trial/placeholder/partial solutions that would require later replacement inside the selected MVP scope;
- MVP may limit scope, but selected-scope solutions must be final/production-quality for that scope;
- non-branching corrections are applied automatically;
- if several options exist but one has a clearly superior durable recommendation, apply it automatically and record rationale;
- only a genuine material product/architecture trade-off becomes `human_decision_required`.

### 4. Execution plan uses the existing Task Engine

After successful Phase 0, Epics create ordered implementation plan items. Every implementation item becomes one ordinary `STANDARD` Task. AI Layer preserves the existing global discipline: one open Task, one active stage and one delegated worker at a time per project.

Epic scheduling decides **which Task is eligible next**. Task Engine alone decides **how that Task executes**, including IMPLEMENT/REVIEW/FIX transitions, worker leases, snapshots, verification, findings and remediation.

### 5. `epic_next` is the authoritative navigator

Weak-model reliability depends on not reconstructing workflow position from chat history. `epic_next` is the durable Epic navigator. When it returns `continue_task`, the orchestrator follows `task_next` only until the linked Task becomes terminal, then returns immediately to `epic_next`.

`memory_context` exposes only compact active-Epic state and points the agent back to `epic_next`; it does not copy the full Epic specification into every prompt.

### 6. Drift is reconciled before future planned work

After Phase 0 and each accepted Epic Task, AI Layer stores a repository identity digest. If the repository changes outside the accepted Epic Task boundary before the next item starts, the Epic blocks normal scheduling and creates a targeted `analysis_only` drift-reconciliation Task.

Only affected remaining assumptions/plan items are reconsidered. The same automatic-correction vs material-human-decision policy as Phase 0 applies.

### 7. The last successful Task is whole-Epic closure/review

The plan always appends a final `STANDARD` Task. Its IMPLEMENT stage updates current project documentation and drafts durable Project Knowledge from current source evidence. Its independent REVIEW stage reviews the **whole implemented Epic** against the execution specification and Definition of Done, not merely the documentation delta of that final Task.

The existing Task Engine review/fix loop owns all findings. Existing Project Knowledge rules remain unchanged: the reviewer must inspect DRAFT cards before PASS and successful review publishes them as VERIFIED.

Epic completion has additional mechanical evidence gates:

- project documentation changed during the final closure Task; and
- at least one Project Knowledge card was actually published by the reviewed Task.

If either is missing, the Epic remains in final review and another final closure/review item is scheduled. Archive is allowed only after mechanical completion.

### 8. Dashboard is read-side only

Dashboard exposes readable current spec, spec history, audits, plan and linked Task states through projections. Dashboard handlers never own Epic transitions or scheduling decisions.

## Consequences

- The user can create, audit and approve a large product decision before any implementation decomposition is frozen.
- Long-running work can continue across chats/models without relying on conversation memory.
- Phase 0 prevents an old discussion from blindly driving current code.
- Full-Epic review catches cross-Task integration gaps that per-Task reviews cannot see alone.
- Documentation and Project Knowledge cannot silently be postponed to a later cleanup phase.
- Task Engine remains the only per-Task execution state machine.

## Rejected alternatives

### Duplicate Epic stage engine
Rejected because it would recreate worker leases, stages, verification and review/fix semantics with a second source of truth.

### Finalize Task decomposition at Epic creation time
Rejected because source may change between planning and implementation; Phase 0 must reconcile reality before the execution plan becomes authoritative.

### Allow temporary architecture under an MVP label
Rejected. MVP is a scope boundary, not permission to implement known throwaway or incomplete selected-scope solutions.

### Ask the user for every Phase 0 mismatch
Rejected because obvious factual corrections and clearly superior durable recommendations do not justify human interruption. Human attention is reserved for genuine material trade-offs.
