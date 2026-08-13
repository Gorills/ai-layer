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

### Local verification contract

`make dev-setup` creates the checkout-owned `.venv` with CPython 3.12, installs development dependencies there and activates the tracked hooks. When that environment exists, Make prepends its `bin` directory to `PATH`; agents do not need to activate it, and repository targets do not silently prefer an ambient AI Layer installation. `make preflight` fails with a setup instruction if `.venv` is absent.

The gate owners are deliberately non-overlapping:

| Command | Proves | Environment |
| --- | --- | --- |
| `make fast-gate` | format, lint and architecture policy | checkout `.venv`; no database |
| `make quality` | deterministic static, unit/integration, governance and release contracts | database-independent; PostgreSQL-marked tests are excluded from an inherited database URL |
| `make postgres-gate` | migrations, constraints, transactions and concurrency | caller-supplied PostgreSQL server; gate-owned migrated test databases |
| `make preflight` | `quality` plus `postgres-gate` on the exact worktree | checkout `.venv` plus an ephemeral Docker PostgreSQL project |

Run focused non-PostgreSQL tests as `.venv/bin/python -m pytest ...`. Do not use SQLite as evidence for PostgreSQL behavior, and do not run PostgreSQL-marked tests directly against an empty shared database: `scripts/postgres_gate.py` owns database creation, migration and cleanup for that suite.

Local `make preflight` creates a unique Compose project, asks Docker for an ephemeral loopback port, reads that actual mapping, and removes its containers, network and volume after success or failure. It ignores inherited `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME` and fixed-port settings. The long-lived `db-up`/`db-down` targets remain separate and use the checkout's ordinary Compose project. Never stop, remove or reuse a container from another checkout merely to make preflight pass; inspect Docker ownership labels and report a cleanup failure if the ephemeral project cannot be removed.

Recovery is bounded to resources whose ownership is known:

- missing `.venv`: run `make dev-setup`; a wrong-version `.venv` must first be moved aside or removed by its owner, then recreated with CPython 3.12;
- unavailable Docker daemon or failed image startup: restore Docker and rerun `make preflight`; do not substitute SQLite or CI;
- interrupted preflight that left resources behind: use the exact project name printed by the runner, verify its `com.docker.compose.project` labels, then run `docker compose --project-name <printed-project> --file docker-compose.yml down --volumes --remove-orphans`;
- controlled external PostgreSQL (CI or diagnostics): set `AI_LAYER_TEST_POSTGRES_URL` and run `make postgres-gate` or `make preflight-ci`; never point it at valuable data because the gate creates and drops databases.

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
