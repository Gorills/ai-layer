# Quality Gates

## Canonical gate

The repository-owned canonical quality entry point is:

```bash
make quality
```

It runs `python scripts/quality_gate.py --deterministic-wheel`. Release creation (`scripts/build_release.py`) runs this deterministic gate before building a runtime archive. It is fail-closed.

Required local stages:

- Ruff formatting check;
- Ruff lint;
- mypy type check;
- architecture/capability/complexity/Epic-boundary gate;
- migration compatibility gate;
- production skill contract gate;
- governance baseline gate;
- unit/integration test suite with global pytest plugin autoload disabled;
- packaging/release gate, including deterministic wheel rebuild and an exact check that the committed installable wheel matches a rebuild from current `src/`.

Missing required tooling is a failure, not a skip. Pytest plugins are not inherited from the workstation: any plugin required by project tests must be an explicit project dependency/configuration.

## Development preflight

Repository development uses the same gate owners locally and in CI:

```bash
make dev-setup     # once per clone: install dev dependencies + activate tracked hooks
make fast-gate     # fast pre-commit feedback
make quality       # deterministic canonical quality gate
make postgres-gate # real PostgreSQL/pgvector hardening
make preflight     # full local pre-push composition
```

`make preflight-ci` composes `make quality` and `make postgres-gate` when `AI_LAYER_TEST_POSTGRES_URL` is already supplied by CI or another controlled environment. GitHub Actions calls these same Make targets rather than duplicating raw gate commands.

The tracked pre-commit hook runs `make fast-gate`; the tracked pre-push hook runs `make preflight`. `make dev-setup` activates them explicitly with `core.hooksPath=.githooks`; installing the runtime package never mutates Git configuration.

A successful preflight applies only to the exact final worktree. Any later code or configuration change invalidates that evidence. Using `--no-verify`, disabling repository hooks, weakening gates, or publishing a known local failure merely to obtain CI diagnostics violates the development contract. An agent without an executable local worktree or the required Docker/PostgreSQL environment must report that limitation instead of claiming preflight success.

## PostgreSQL hardening gate

CI also runs `make postgres-gate` against a real PostgreSQL 16 + pgvector service using `AI_LAYER_TEST_POSTGRES_URL`. It creates isolated databases and proves:

1. fresh database -> `alembic upgrade head`;
2. minimum supported pre-Epics schema `0010_adaptive_task_workflow` -> `head`;
3. PostgreSQL-only constraints/transaction semantics;
4. two-session Task creation and stage-completion races without relying on filesystem locks;
5. worker-recovery race behavior;
6. durable snapshot recovery in a new database session.

SQLite remains useful for fast tests, but cannot satisfy this production-persistence gate.

## Architecture policy

Built-in ceilings cannot be loosened by editing JSON policy. Current absolute ceilings are 500 lines for ordinary production modules, 550 for composition roots, 120 lines / 80 statements for a function, cyclomatic complexity 24 and nesting 5. Ordinary modules above 300 lines produce soft maintainability warnings. There are no active no-growth ratchets in this release candidate.

The architecture gate rejects internal import cycles, capability cycles, unowned modules and forbidden capability edges such as Interfaces -> Infrastructure and Dashboard -> Task/Skill/DB internals. It also protects the pre-Epics boundary against ownership of TaskStage/worker-lease/verification/review-fix/remediation/repository-snapshot/finding primitives.

## Governance-sensitive changes

`release/governance-policy.json` marks architecture policy/gates, development bootstrap/hooks/CI, installer/bootstrap trust-chain files, release gates, migration policy, task-state invariants and verification runner as protected governance material. The local hash baseline is only tamper-evident convenience; it is deliberately not presented as a security boundary.

Semantic changes to protected files require a human-visible rationale/ADR, tests, a deliberately refreshed baseline and external protected-branch review. Production enforcement requires required CI and a release-signing identity outside ordinary feature-agent write access.

## Release repository vs runtime artifact

The development repository may contain `.github`, `.githooks`, maintainer scripts, tests and architecture configuration. `scripts/build_release_archive.py` owns the runtime allowlist/exclusions. Runtime release cleanliness is therefore a packaging property, not a ban on normal development tooling.
