---
slug: legacy-change
description: Behavior-preserving legacy modification discipline for discovery, characterization, narrow seams, regression control and incremental cleanup.
kind: core
keywords:
- legacy
- refactor
- existing behavior
- characterization test
- compatibility
- seam
- regression
- technical debt
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Legacy Change Skill

## Apply when

Use when changing poorly documented, tightly coupled, high-risk or old code where current behavior is only partially understood. Also use when a “simple” change crosses many files, relies on implicit conventions, or risks breaking consumers not represented in modern tests.

## Core contract

- Discover before redesign. In legacy systems, actual callers, data and side effects outrank intended architecture.

- Separate the requested behavior change from cleanup. Make only the refactor necessary to create a safe seam unless broader restructuring is explicitly in scope.

- Characterize important current behavior before changing it, including odd behavior that may be relied upon.

- Trace from all entry points to side effects; legacy code often has parallel cron/CLI/webhook/admin paths invisible from the primary endpoint.

- Preserve public and persisted contracts by default: data shape, error semantics, ordering, identifiers, timing assumptions and side effects.

- Use narrow adapters/seams to isolate unstable legacy dependencies; do not wrap the entire legacy system in a new abstraction layer without purpose.

- Prefer incremental replacement with a single canonical transition path over a big-bang rewrite or permanent dual implementation.

- Inspect historical migrations/configuration and real data assumptions before changing schema or normalization.

- Add diagnostics where the legacy path is opaque, but do not introduce sensitive logging or change runtime behavior just for observability.

- After the change, remove dead transition code you can prove unused; do not leave duplicated old/new paths “just in case”.

## Evidence to inspect

- Callers found by code search, routes/commands/workers/schedulers and dynamic registration/configuration.

- Existing tests plus production bug reports, fixtures, snapshots and historical compatibility cases.

- Database schema, migrations and representative persisted values, including null/sentinel/legacy encodings.

- Git history around surprising code to distinguish accidental complexity from deliberate compatibility.

- External consumers, templates, scripts or integrations that depend on current outputs/side effects.

- Runtime logs/metrics/traces where static analysis cannot reveal dynamic dispatch or data-dependent branches.

## Decision rules

- If behavior is unclear but externally visible, write characterization evidence before simplifying it.

- If a change requires touching unrelated areas, search for a narrower seam or canonical shared operation before accepting the broad blast radius.

- If old and new implementations would coexist, define routing authority, migration state and deletion condition; avoid indefinite dual writes.

- If a strange branch has no obvious caller, prove it unused through search/tests/runtime evidence before deletion.

- If data cleanup is needed, separate schema compatibility from backfill and enforce the new invariant only after data is ready.

- If the legacy API is consumed externally, prefer additive compatible evolution and deprecation over silent semantics changes.

- If the safest seam is a small adapter around a hard dependency, accept localized imperfection rather than “cleaning” the whole subsystem.

- If a rewrite cannot be validated against representative behavior/data, reject it as unverifiable scope.

## Workflow

1. Map entry points, callers, state reads/writes and external side effects for the requested behavior.

2. List known and uncertain contracts; identify which uncertainties could break users or data.

3. Create characterization/regression tests around the high-risk behavior using representative data.

4. Choose the narrowest seam that allows the requested change without duplicating the business flow.

5. Implement the behavior change first; keep opportunistic cleanup mechanically safe and reviewable.

6. Run old/new compatibility and failure cases, including data created by older versions where relevant.

7. Search for bypasses, duplicate writers and dead compatibility code after the new path is in place.

8. Document only the durable invariant/transition decisions future maintainers need, not a narrative of the refactor.

## Implementation patterns

- Characterization tests can assert current behavior without endorsing it; label unintuitive compatibility intentionally.

- Branch-by-abstraction works when the abstraction is small and temporary; record the removal trigger.

- Strangler-style replacement is appropriate around externally bounded subsystems, not as an excuse to maintain two internal flows forever.

- Introduce typed boundary objects around unstructured legacy dictionaries when it reduces ambiguity without forcing a full domain rewrite.

- Use database constraints only after legacy data has been audited/backfilled to satisfy them.

- Keep compatibility parsing at the edge and normalize to one internal representation as early as possible.

- Extract pure decision functions from side-effect-heavy code to gain test seams without altering orchestration first.

- When historical quirks must remain, add a focused comment/test explaining the external contract rather than preserving mystery.

## Failure modes

- Clean rewrite: old code is discarded because new code is prettier, with no behavioral equivalence evidence. Characterize first.

- Refactor avalanche: a feature becomes a repository-wide cleanup. Re-establish the minimal seam and separate work.

- Hidden secondary entry point: web path is fixed while worker/CLI still uses old logic. Trace all dispatch paths.

- Dual-write forever: old/new stores or flows both receive mutations with no reconciliation/removal plan. Define authority and cutover.

- Schema-first break: a NOT NULL/enum/rename lands before legacy data/callers are compatible. Use expand/backfill/contract.

- Dead-code guess: dynamic registration/reflection makes static search incomplete. Add runtime/config evidence before deletion.

- Compatibility normalization everywhere: every layer handles old/new formats. Normalize once at the boundary.

- Mocked legacy proof: tests fake the subsystem whose odd behavior causes risk. Include a representative integration/characterization path.

## Verification

- Run characterization tests against the pre-change behavior when possible and confirm the new implementation preserves intended contracts.

- Exercise every discovered entry point that reaches the changed legacy capability.

- Use representative old data/schema states, not only newly generated ideal fixtures.

- Compare side effects, ordering, errors and externally visible payloads across important scenarios.

- Search for remaining bypass/duplicate paths and prove whether they are intentional.

- Run canonical repository quality gates plus targeted integration tests around the seam.

- Review diff for unrelated cleanup and revert changes that increase review surface without reducing risk.

- If dynamic/runtime behavior remains unverified, state the exact gap instead of claiming full preservation.

## Completion criteria

- The requested behavior is implemented through one identified canonical path or a bounded temporary transition.

- Important pre-existing contracts are characterized and preserved or explicitly changed with compatibility handling.

- Legacy data and secondary entry points were included in verification.

- No broad rewrite or cleanup was smuggled into scope without evidence and acceptance criteria.

- Temporary seams/compatibility code have an owner and deletion condition.

- Residual unknown behavior is explicit and proportionate to the release risk.

## Related skills and escalation

- Use `architecture` when the legacy change requires durable boundary redesign.

- Use `compatibility` and `database-migrations` for version/schema transition details.

- Use `testing` for characterization strategy and `source-first` for historical framework behavior.

- Escalate when behavior cannot be characterized and failure would risk irreversible data loss or external contract breakage.
