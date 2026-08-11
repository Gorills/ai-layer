# Roadmap

## Promotion gate for v0.10.3 pre-Epics hardening

Before Epic implementation starts, run the already-wired promotion checks on the supported environment:

1. CPython 3.12 canonical quality gate with pinned dependencies, Ruff and mypy.
2. PostgreSQL 16 + pgvector `scripts/postgres_gate.py`, including fresh `head`, supported `0011 -> head`, cross-session Task/stage/recovery races and snapshot persistence.
3. Real daemon/service restart and active-Task/expired-worker recovery under `systemd --user`.
4. Real supported-host MCP/dashboard Task workflow smoke test.
5. Production signed update-channel black-box when publisher infrastructure is available.

These are validation/promotion items. Do not add more foundation architecture to compensate for an environment that has not run the gates.

## Next capability: Epics

Only after the promotion gate is green, implement Epics as a separate capability over public Task application contracts.

Initial Epic scope may include Epic identity, plan versions, WorkItems, dependency DAG, Epic-level approvals/acceptance, progress aggregation and integration review. The Epic scheduler chooses which Task may start. It must not duplicate TaskStage, worker leases, repository snapshots, verification, review/fix remediation, findings, idempotent Task command handling or Task state transitions.

Repository-level parallel mutation remains a separate future capability. Do not infer that DB-safe concurrent control-plane requests make simultaneous repository writers safe; worktrees/merge/conflict/provenance policy must be designed and verified before enabling parallel mutating workers.
