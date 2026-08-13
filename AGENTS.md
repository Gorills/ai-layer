# AI Layer Repository Agent Contract

This file is the mandatory root bootstrap for any coding agent that edits this repository.
Repository source, tests, migrations and executable gates are authoritative; prose is guidance, not proof.

## Self-hosting isolation — mandatory

This source repository is intentionally **not registered as an AI Layer target project** while AI Layer itself is being developed. The AI Layer installed or running elsewhere on the machine may be an older, incompatible release and is outside the evidence boundary for repository work.

- Do not call installed AI Layer project tools (`project_status`, `project_search`, Tasks, Epics, Knowledge, Project Map, Dashboard or other MCP/control-plane tools) for this repository.
- Do not inspect or infer current repository behavior, work state, continuation, rules or architecture from a machine AI Layer registry, database, Dashboard, runtime, logs, generated project state, `~/.ai-layer`, or another global installation.
- Do not run a globally installed `ai-layer` or `ai-layer-mcp` executable as the implementation under development. Use this checkout's source, its repository-owned `.venv`, tests, migrations and scripts.
- Global agent skills may be used as professional guidance only. They do not provide repository state and never override current source, this file, accepted ADRs or executable gates.
- Installation, upgrade and compatibility tests may exercise a built artifact only when the test explicitly requires it. Isolate its home/runtime/database and version; never reuse ambient machine AI Layer state as test evidence.

If ambient AI Layer output conflicts with this checkout, ignore the ambient output. Current checkout source and repository verification are authoritative.

## Before editing

1. Read `MAINTAINER_INSTRUCTIONS.md`, `PROJECT_CHARTER.md`, `PRODUCT_GOAL.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `QUALITY_GATES.md`, `CURRENT_STATE.md`, and relevant ADRs in `DECISIONS/`.
2. Inspect the actual source, tests, migrations and current diff for the requested change.
3. Identify the owning capability and preserve existing boundaries. Do not create parallel workflow engines, speculative routers or convenience bypasses.
4. In a fresh local clone, run `make dev-setup` once. It installs development dependencies and activates the repository-owned Git hooks.

## Development loop

- Follow the canonical local verification contract in `QUALITY_GATES.md`. Use `make dev-setup` once per checkout; Make then selects the repository `.venv`. Do not repair Docker conflicts by stopping or deleting containers owned by another checkout.
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

## Mandatory completion handoff

Every final response after completed repository work must include both of these user-visible sections:

1. **What next** — name the next concrete recommended repository action, or state explicitly that no required work remains. Do not imply that commit, push, publication, deployment or external review happened unless it actually did.
2. **Prompt for the next chat** — provide a ready-to-copy, self-contained prompt that tells a fresh agent what outcome to pursue next, where to recover current source/worktree context, which constraints matter and which verification evidence already exists. The prompt must tell the next agent to inspect current source and Git state rather than trust the handoff as code truth.

Do not omit this handoff because the implementation is complete, the next action is optional or the current context feels sufficient. If no follow-up is required, provide a prompt for an optional final audit, publication step or the user's next chosen objective without inventing unfinished work.

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
- `make preflight` — local full pre-push verification using an ephemeral checkout-owned Docker PostgreSQL project.
- `make preflight-ci` — full gate composition when `AI_LAYER_TEST_POSTGRES_URL` is already supplied (CI/controlled environments).
