# ADR 0001 — Capability boundaries before Epics

**Status:** accepted for the v0.9.0 candidate.

## Context

Task, CLI, MCP, Dashboard, Skill and repository responsibilities had accumulated in large modules and package-level cycles could exist even when a file-level import-cycle test passed.

## Decision

Use explicit capability ownership enforced by `scripts/architecture_gate.py`. Interfaces call application use cases; Dashboard consumes projections; repository operations and verification are separate capabilities; Task Engine does not depend on Dashboard/Interfaces/Epics. Preserve small compatibility facades only where needed for public/import stability.

## Consequences

Adding an Epic, host or skill should add a focused adapter/capability instead of extending a central service. The architecture policy is governance-sensitive and may only be tightened by normal changes.
