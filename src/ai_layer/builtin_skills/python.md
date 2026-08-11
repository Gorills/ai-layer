---
slug: python
description: Python runtime, packaging, async/resource lifecycle, configuration, typing
  and test discipline for services and tooling.
kind: stack
keywords:
- python
- pytest
- asyncio
- typing
- pyproject
- venv
- packaging
- async
- type hint
- virtualenv
- pydantic
- python package
entry_sections:
- Apply when
- Core contract
---
# Python Skill

## Apply when
Python source, packaging/dependencies, runtime/process behavior, async/concurrency, configuration or Python tests change.

## Core contract
- Follow the project-pinned Python version, dependency manager/lock ownership, formatter/linter/type checker and test runner.
- Keep sync/async boundaries explicit; do not block event loops with avoidable synchronous I/O.
- Own resource lifetime with context managers/finally and cancellation-safe cleanup; avoid hidden global DB/client/session lifecycle.
- Keep configuration loading centralized according to the project and never depend accidentally on process cwd for project identity/files.
- Preserve existing architectural conventions before introducing repositories/services/result wrappers or a new package manager.
- Catch exceptions only where the layer can recover/translate/add useful context; never swallow broad exceptions for “stability”.

## Packaging and environments
Respect `pyproject.toml`, existing lock files and virtual-environment strategy. Do not edit generated lock files manually. Avoid `sys.path` hacks and import behavior that only works from one shell cwd. Public packages/services should have explicit entry points and predictable installed behavior.

## Async and concurrency
Choose asyncio/threads/processes from actual I/O/CPU semantics and the existing runtime. Do not share non-thread-safe sessions/clients across concurrency domains. Cancellation/timeouts/retries must leave resources and state consistent. Avoid holding DB transactions open while awaiting slow external services without an explicit design.

## Types and data models
Use explicit boundary models/types where they improve contract clarity and match project style. Runtime input still needs validation; type hints do not sanitize external data. Avoid annotation churn across unrelated legacy modules.

## Configuration and side effects
Avoid import-time network/database/filesystem mutations. Keep environment reads and process-global configuration at deliberate composition boundaries. Logging must not expose secrets or huge payloads.

## Testing
Control time/randomness/environment in tests. Use real persistence/protocol integration where mocks cannot prove behavior. A fixed reproducible bug gets a regression test when practical.

## Quality gate
Run configured lint/type/tests and relevant service/CLI smoke checks. For async/persistence/process changes, exercise the real lifecycle boundary and report environment-limited checks explicitly.
