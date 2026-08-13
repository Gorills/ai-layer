# ADR 0024 — Checkout-owned local verification

## Status

Accepted for repository development.

## Context

Repository verification could accidentally use tools from the ambient shell because Make invoked unqualified executables. Local preflight also reused the long-lived Compose service's fixed global container name and host port. A different AI Layer checkout could therefore block the canonical gate even though its database was unrelated and had to remain untouched. Agents needed private chat context and ad hoc Compose overrides to distinguish a product failure from test-environment ownership.

The quality suite and the PostgreSQL suite also have different setup contracts. General tests must remain database-independent, while PostgreSQL-marked tests require fresh and supported-upgrade databases migrated by the owning gate.

## Decision

`QUALITY_GATES.md` is the canonical local verification contract. `make dev-setup` creates and installs development dependencies into the repository `.venv`; Make automatically prepends that environment when it exists, and local preflight fails clearly when it does not.

`make quality` owns database-independent static, test, governance and release evidence. It removes inherited `AI_LAYER_TEST_POSTGRES_URL` from its pytest stage. `make postgres-gate` exclusively owns PostgreSQL-marked tests and creates, migrates and cleans isolated test databases. `make preflight-ci` composes those owners for CI or another controlled database.

`make preflight` uses a repository-owned runner that starts a unique Compose project on a Docker-assigned loopback port, discovers the actual port, runs `preflight-ci`, and removes only that project's containers, network and volume in a finally path. Inherited Compose project/file and fixed-port settings do not alter this local gate. The ordinary `db-up`/`db-down` service remains long-lived and separate.

The development Compose file has no global `container_name` and supports a configurable ordinary host port. A preflight conflict must never be repaired by stopping, removing or adopting Docker resources belonging to another checkout.

## Consequences

- A new agent can reproduce the full local gate from repository documentation without ambient machine knowledge.
- Parallel or older checkouts no longer collide through one global container name or fixed preflight port.
- PostgreSQL evidence always crosses the real migrated database boundary once, under its owning gate.
- Local preflight leaves no database volume behind after success or failure; a cleanup failure is itself a gate failure.
- Runtime/upgrade compatibility with legacy fixed-name containers remains handled explicitly by the existing runtime compatibility path.
