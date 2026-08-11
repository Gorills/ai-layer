# Roadmap

## v0.12.0 — Epics v1

The first complete Epic capability is implemented in source. Its scope is intentionally narrow and complete rather than framework-like:

- versioned human-readable specification;
- unlimited pre-approval audits and revisions;
- explicit human approval baseline;
- mandatory source-authoritative Phase 0;
- automatic obvious/strong-recommendation reconciliation and human attention only for genuine material trade-offs;
- post-Phase0 sequential STANDARD Task plan;
- repository-drift reconciliation;
- mandatory final documentation + Project Knowledge + whole-Epic independent review;
- mechanical completion/archive gates;
- `epic_next` weak-model navigation, native `epics` skill and compact memory-context recovery;
- Dashboard spec/audit/plan/history read views.

Epics remain a scheduler over the existing Task Engine. They do not duplicate TaskStage, worker leases, repository snapshots, verification, review/fix remediation, findings or Task transitions.

## Promotion gate for v0.12.0

Before treating Epics v1 as fully promoted on a working machine, run the already-wired release checks plus real supported-host field acceptance:

1. CPython 3.12 canonical quality gate with pinned dependencies, Ruff, mypy, deterministic source-fresh wheel and full tests.
2. PostgreSQL 16 + pgvector `scripts/postgres_gate.py`, including the declared supported `0010_adaptive_task_workflow -> head` migration path through `0014_epics_v1`.
3. Clean install/update of the 0.12.0 wheel and correct installed version/schema.
4. Real daemon/service restart and active-Task/expired-worker recovery under `systemd --user`.
5. Real MCP/dashboard Task smoke plus a real Epic black-box flow: create → audit/revise → explicit approval → Phase 0 → plan → sequential STANDARD Tasks → final whole-Epic review → documentation/Project Knowledge closure → archive.
6. Context-loss/new-chat recovery: `memory_context` exposes active Epic and a weak model resumes from `epic_next` rather than inventing a parallel Task.
7. Repository-drift black-box during an Epic and targeted reconciliation before future work.
8. Multi-project reconcile/sync behavior with an active/archived Epic present.
9. Production signed update-channel black-box when publisher infrastructure is available.

These are validation/promotion items. Do not add another architecture-hardening phase unless field acceptance exposes a concrete defect.

## After Epics v1

Use Epics in real projects before extending scope. Potential future capabilities must be justified by field evidence. Repository-level parallel mutation remains separate: DB-safe concurrent control-plane requests do not make simultaneous repository writers safe; worktrees/merge/conflict/provenance policy must be explicitly designed and verified before any parallel mutating workers are enabled.
