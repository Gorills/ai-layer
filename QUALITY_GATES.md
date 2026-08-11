# Quality Gates

## Canonical gate

```bash
python scripts/quality_gate.py --deterministic-wheel
```

Release creation (`scripts/build_release.py`) runs this gate before building a runtime archive. It is fail-closed.

Required local stages:

- Ruff formatting check;
- Ruff lint;
- mypy type check;
- architecture/capability/complexity/Epic-boundary gate;
- migration compatibility gate;
- production skill contract gate;
- governance baseline gate;
- unit/integration test suite with global pytest plugin autoload disabled;
- packaging/release gate, including deterministic wheel rebuild.

Missing required tooling is a failure, not a skip. Pytest plugins are not inherited from the workstation: any plugin required by project tests must be an explicit project dependency/configuration.

## PostgreSQL hardening gate

CI also runs `python scripts/postgres_gate.py` against a real PostgreSQL 16 + pgvector service using `AI_LAYER_TEST_POSTGRES_URL`. It creates isolated databases and proves:

1. fresh database -> `alembic upgrade head`;
2. previous supported pre-Epics schema `0011_pre_epics_foundation` -> `head`;
3. PostgreSQL-only constraints/transaction semantics;
4. two-session Task creation and stage-completion races without relying on filesystem locks;
5. worker-recovery race behavior;
6. durable snapshot recovery in a new database session.

SQLite remains useful for fast tests, but cannot satisfy this production-persistence gate.

## Architecture policy

Built-in ceilings cannot be loosened by editing JSON policy. Current absolute ceilings are 500 lines for ordinary production modules, 550 for composition roots, 120 lines / 80 statements for a function, cyclomatic complexity 24 and nesting 5. Ordinary modules above 300 lines produce soft maintainability warnings. There are no active no-growth ratchets in this release candidate.

The architecture gate rejects internal import cycles, capability cycles, unowned modules and forbidden capability edges such as Interfaces -> Infrastructure and Dashboard -> Task/Skill/DB internals. It also protects the pre-Epics boundary against ownership of TaskStage/worker-lease/verification/review-fix/remediation/repository-snapshot/finding primitives.

## Governance-sensitive changes

`release/governance-policy.json` marks architecture policy/gates, installer/bootstrap trust-chain files, release gates, migration policy, task-state invariants and verification runner as protected governance material. The local hash baseline is only tamper-evident convenience; it is deliberately not presented as a security boundary.

Semantic changes to protected files require a human-visible rationale/ADR, tests, a deliberately refreshed baseline and external protected-branch review. Production enforcement requires required CI and a release-signing identity outside ordinary feature-agent write access.

## Release repository vs runtime artifact

The development repository may contain `.github`, maintainer scripts, tests and architecture configuration. `scripts/build_release_archive.py` owns the runtime allowlist/exclusions. Runtime release cleanliness is therefore a packaging property, not a ban on normal development tooling.
