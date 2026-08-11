# ADR 0014 — Repository-native development self-governance

- Status: Accepted
- Date: 2026-08-11

## Context

AI Layer already had strong canonical CI gates, but the repository did not make those gates the normal local development path. `MAINTAINER_INSTRUCTIONS.md` was not a native bootstrap file for every supported coding agent, `make quality` was weaker than CI because it omitted deterministic-wheel verification, and CI duplicated raw commands instead of consuming repository-owned targets.

This allowed an inefficient feedback loop: edit -> push -> discover formatting/architecture/governance failure in CI -> patch -> push again. It also left parts of the quality trust chain outside `release/governance-policy.json`, so an ordinary feature change could theoretically weaken CI/configuration rather than satisfy it.

## Decision

1. `AGENTS.md` is the canonical root development/publication contract for coding agents. It is concise and links to the deeper repository documents rather than duplicating architecture.
2. `GEMINI.md` imports `AGENTS.md`, keeping Gemini CLI on the same contract without a second policy copy.
3. `make dev-setup` explicitly activates tracked `.githooks` and installs development dependencies. Package installation itself does not mutate Git configuration.
4. The pre-commit hook runs `make fast-gate` (format, lint, architecture) for short feedback.
5. The pre-push hook runs `make preflight`, which starts/waits for the repository PostgreSQL service and runs the same `make quality` + `make postgres-gate` owners used by CI.
6. `make quality` is exactly the deterministic canonical quality gate. GitHub Actions invokes Make targets instead of duplicating gate commands.
7. A successful preflight is evidence for the exact final worktree only. A later code/configuration change invalidates it.
8. Missing local execution capability is fail-closed for publication: an agent may not claim preflight passed or use CI as its first feedback loop.
9. The tamper-evident governance set expands to include the agent bootstrap, local hooks/targets, CI workflow, project tool configuration, PostgreSQL/skill gates, and the regression test that checks this contract.
10. Root agent bootstrap files and `.githooks` are explicitly valid development-repository artifacts but remain excluded from runtime release archives.

## Consequences

- Ordinary local development gets fast failures before commit and full parity before network publication.
- CI remains an independent clean-environment backstop and protected-branch enforcement point; local hooks are not treated as a security boundary.
- New clones require one explicit `make dev-setup`.
- A full pre-push requires Docker Compose and the repository PostgreSQL/pgvector service.
- Changes to development-governance files intentionally require ADR/rationale, baseline refresh and protected review.
- No runtime dependency, target-project footprint or AI Layer Task Engine behavior changes.
