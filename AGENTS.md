# AI Layer Repository Agent Contract

This file is the mandatory root bootstrap for any coding agent that edits this repository.
Repository source, tests, migrations and executable gates are authoritative; prose is guidance, not proof.

## Before editing

1. Read `MAINTAINER_INSTRUCTIONS.md`, `PROJECT_CHARTER.md`, `ARCHITECTURE.md`, `QUALITY_GATES.md`, `CURRENT_STATE.md`, and relevant ADRs in `docs/DECISIONS/`.
2. Inspect the actual source, tests, migrations and current diff for the requested change.
3. Identify the owning capability and preserve existing boundaries. Do not create parallel workflow engines, speculative routers or convenience bypasses.
4. In a fresh local clone, run `make dev-setup` once. It installs development dependencies and activates the repository-owned Git hooks.

## Development loop

- Use focused tests/checks while iterating.
- Before committing a code or governance change, run `make fast-gate`. The installed pre-commit hook enforces the same fast gate.
- After the final code change and before any push or PR publication, run `make preflight`.
- Any code/configuration change after a successful preflight makes that evidence stale; rerun `make preflight`.
- A failed or unavailable required gate is a blocker, not permission to publish and let CI diagnose it.

## Publication rules

- CI is the final independent backstop, not the first lint/test feedback loop.
- Never use `--no-verify`, disable repository hooks, weaken a gate, raise a limit, remove a check, or change test configuration merely to make a feature pass.
- Do not push or open/update a PR with production changes known to fail `make preflight`.
- Do not claim local verification if you do not have an executable local worktree and the required Docker/PostgreSQL environment. In that environment, stop before publication and report the limitation.
- Keep commits and PRs focused; do not include unrelated dirty-worktree changes.

## Governance-sensitive changes

`release/governance-policy.json` defines tamper-evident governance files. Semantic changes to those files require:
- a human-visible rationale;
- an ADR;
- tests proving the intended invariant;
- a deliberately refreshed governance baseline;
- protected-branch review with the required CI checks.

Ordinary feature work must not modify governance files to obtain a green result.

## Canonical commands

- `make dev-setup` — install dev dependencies and activate tracked hooks.
- `make fast-gate` — fast local feedback: format, lint and architecture.
- `make quality` — the exact deterministic canonical quality gate used by CI.
- `make postgres-gate` — the PostgreSQL/pgvector hardening gate used by CI.
- `make preflight` — local full pre-push verification using the repository Docker PostgreSQL service.
- `make preflight-ci` — full gate composition when `AI_LAYER_TEST_POSTGRES_URL` is already supplied (CI/controlled environments).
