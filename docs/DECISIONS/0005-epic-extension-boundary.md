# ADR 0005 — Epic is a new capability, not a Task feature

**Status:** accepted and mechanically protected for the pre-Epics foundation.

## Context

Future Epics need planning, dependency scheduling, acceptance aggregation and integration gates without turning Task service into an orchestration god object or creating a second Task Engine.

## Decision

Reserve `ai_layer.epics` as an empty capability boundary only. Future Epic scheduling decides **which Task may run**. The existing Task Engine decides **how one Task executes reliably**.

Epic code may eventually own Epic planning, plan versions, dependency DAGs, approvals/acceptance at Epic scope, progress aggregation and integration review. It must not own or reimplement per-Task worker leases, TaskStage lifecycle, Task repository snapshots, Task verification, reviewer/fixer remediation loops, review findings, or a second task-like state machine/source of truth.

The architecture policy forbids the pre-Epics boundary from depending directly on Task internals, persistence, workspace/snapshot or verification capabilities. `scripts/architecture_gate.py` additionally rejects future Epic-owned classes/functions named like protected per-Task lifecycle primitives. Public application contracts may be introduced when Epics are actually implemented; no Epic database tables, CRUD, planner, scheduler or dashboard behavior are added now.
