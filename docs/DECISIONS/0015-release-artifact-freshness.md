# ADR 0015 — Release artifacts must match current source

- Status: Accepted
- Date: 2026-08-11

## Context

The supported installer installs the committed deterministic application wheel from `dist/`. Runtime source continued to change after the 0.11.4 wheel was committed, while the existing release checks only proved that the committed wheel matched its manifest hash and that two fresh rebuilds matched each other. They did not prove that the committed wheel matched a rebuild from the current source tree. This allowed CI to pass while `install.sh` installed stale runtime code.

The release manifest also declares `0010_adaptive_task_workflow` as the minimum supported schema, while the real PostgreSQL promotion gate started its upgrade-path check at `0011_pre_epics_foundation`.

## Decision

1. Release 0.11.5 refreshes the committed wheel from current source and updates the manifest hash/path.
2. Canonical tests rebuild the application wheel from current source and require byte equality with the committed installable wheel. Any runtime/source/version change without a wheel refresh therefore fails `make quality`.
3. The real PostgreSQL hardening gate verifies the declared minimum supported migration path `0010_adaptive_task_workflow -> head`.
4. No new release framework, artifact registry, or workflow engine is introduced. The existing deterministic builder, manifest and PostgreSQL gate remain the owners of these checks.

## Consequences

- `main` cannot remain green with a stale installable wheel.
- The supported installer and audited source represent the same runtime bytes.
- The declared migration compatibility floor is exercised on real PostgreSQL rather than only described statically.
- Future runtime changes must refresh the wheel and manifest as part of the same release change.
