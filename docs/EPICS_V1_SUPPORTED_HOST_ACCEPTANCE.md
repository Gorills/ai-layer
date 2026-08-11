# Epics v1 — supported-host acceptance

This checklist is the promotion/field-validation contract for `0.12.0`. It does not replace canonical CI and must be executed on a supported Linux x86_64 / CPython 3.12 host against the installed release.

## Install and runtime

- Clean-install or update the committed `0.12.0` release artifact.
- Confirm the installed wheel SHA-256 matches `release/release-manifest.json` before running black-box acceptance.
- Confirm `ai-layer` reports `0.12.0` and Alembic reaches `0014_epics_v1` without resetting existing Project/Task/Knowledge state.
- Confirm the user service, persistent core, MCP bridge and Dashboard recover after a real `systemd --user` restart.

## Real Epic black-box

Use a disposable or real test project and natural agent instructions rather than internal Python calls.

1. Discuss a non-trivial product change until the intended final behavior is clear, then ask the agent to create an Epic.
2. Confirm Dashboard shows a readable complete specification and immutable version history.
3. Request at least one independent audit; revise the spec; explicitly approve it. Also verify an already-approved-but-not-started spec can be audited again and any revision requires reapproval.
4. Confirm the first execution Task is always read-only Phase 0 and no implementation plan exists before it completes.
5. Confirm Phase 0 checks current source, completeness and selected-scope finality; obvious/strongly recommended corrections update the execution spec automatically.
6. Exercise a genuine material decision once: Epic must stop for the user and continue through the same reconciliation context after the choice, without recreating completed history.
7. Confirm the generated work items execute sequentially as ordinary STANDARD Tasks through independent REVIEW and, when forced, FIX -> REVIEW.
8. Change repository state between accepted Task boundaries and confirm targeted drift reconciliation occurs before the next planned Task. Also test a change immediately after Task/Phase-0 completion but before the next `epic_next`; it must not be silently accepted.
9. Start a fresh/weak-model chat during the Epic. `memory_context` must expose compact active-Epic state and the agent must recover by following `epic_next`, not by reconstructing workflow position from chat memory.
10. Confirm the final successful Task updates relevant project documentation and Project Knowledge, then independently reviews the whole Epic against the execution specification/Definition of Done.
11. Force a failed mechanical closure once (for example missing reviewed Project Knowledge) and confirm another final-review attempt is scheduled instead of archive.
12. After PASS, confirm archive preserves spec versions, audits, Phase 0/drift history, linked Tasks and final-review evidence.

## Recovery and project hygiene

- Interrupt/restart the core/service while an Epic-linked Task is active; Task Engine recovery must remain authoritative and Epic must resume through `task_next` -> `epic_next`.
- Exercise worker disconnect/lease expiry during an Epic-linked Task and verify no orchestrator fallback mutation or retrospective attribution occurs.
- Run multi-project reconcile/sync with an active or archived Epic present.
- Run `ai-layer doctor --all-projects` and confirm no new target-repository AI Layer footprint appears beyond the configured standard/external/strict-private contract.

Only after these checks pass should `0.12.0` be called fully promoted on a supported host. Failures should produce concrete fixes; they are not a reason for another speculative architecture-hardening phase.
