# ADR 0021 — Self-hosting development isolation

## Status

Accepted for repository development.

## Context

AI Layer is both the product implemented by this repository and a tool that may already be installed on a contributor machine. The ambient installation can be an older release with different schemas, bootstrap rules, project registrations, Dashboard projections and MCP contracts. Treating that installation as durable context for development of a newer checkout can silently mix two versions and make agents follow stale state or validate the wrong implementation.

The source repository is intentionally not registered as an AI Layer target during self-hosting development. Global professional skills remain useful because they are methodology, not project state.

## Decision

Repository development uses a closed evidence boundary: current checkout source, tests, migrations, accepted repository ADRs and repository-owned verification scripts. Agents must not call ambient AI Layer project/control-plane tools for this checkout or inspect an ambient registry, database, Dashboard, runtime, logs or generated state to reconstruct repository work.

The globally installed `ai-layer` and `ai-layer-mcp` executables are not the implementation under test. Development commands run from the repository-owned virtual environment. Global agent skills may guide engineering practice, but their content is non-authoritative and cannot supply repository state.

Host-native `.agents` and `.codex` mount points may exist in a development checkout. Release packaging treats them as development-environment artifacts and excludes them from the runtime archive rather than confusing their presence with AI Layer product state.

An installation, upgrade or compatibility test may execute a locally built artifact when that boundary is the explicit subject of the test. Such tests use isolated home, runtime and database locations and identify the tested artifact/version; ambient machine state is never accepted as evidence.

## Consequences

- New agents cannot accidentally resume stale Tasks/Epics or trust an obsolete Project Map for this checkout.
- Tests and diagnostics exercise the source/artifact being developed rather than whichever version happens to be installed globally.
- Global skills remain available without importing global AI Layer state or runtime contracts.
- Cross-version installation behavior remains testable through explicit isolated compatibility harnesses.
