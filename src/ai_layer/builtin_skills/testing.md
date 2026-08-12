---
slug: testing
description: Risk-based testing discipline for behavior, invariants, boundaries, concurrency, failures and maintainable evidence rather than test-count theater.
kind: core
keywords:
- testing
- unit test
- integration test
- e2e
- property test
- contract test
- regression
- fixture
- mock
- coverage
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Software Testing Skill

## Apply when

Use when implementing or reviewing behavior, fixing bugs, changing contracts, refactoring risky code or deciding what verification gives credible evidence. Use especially when existing tests pass but the change touches concurrency, persistence, external services or user-visible workflows.

## Core contract

- Test risk and observable behavior, not implementation trivia. A high line-coverage number can coexist with untested invariants and failure modes.

- Choose the lowest test level that can prove the claim, but cross real boundaries where boundary behavior is the thing at risk.

- A regression test must fail for the original defect or an equivalent controlled reproduction before relying on it as evidence.

- Prefer deterministic tests with explicit time, randomness, identifiers and external dependencies. Flakiness is a product defect in the verification system.

- Mock collaborators only to isolate a deliberate boundary or force rare outcomes; do not mock the code under test into confirming its own assumptions.

- Use real database semantics for transactions, constraints, SQL and migrations; in-memory substitutes do not prove database behavior.

- Test error, retry, duplicate, empty, maximum and concurrency cases whenever the production environment can produce them.

- Assertions should describe externally meaningful outcomes and durable side effects, including what must *not* happen.

- Fixtures/builders should expose intent and minimize irrelevant setup. Giant shared fixtures create invisible coupling between tests.

- Keep tests diagnostic: failures should identify the violated behavior without requiring manual log archaeology.

## Evidence to inspect

- Changed code paths and acceptance criteria, especially invariants, boundaries and new branches.

- Existing tests around the capability, their fixture architecture and known gaps/flaky markers.

- Production bug report, stack trace or observed failure sequence for regression work.

- Database constraints/migrations, external contracts and queue/retry behavior touched by the change.

- Test runner configuration, isolation strategy, parallelism and environment dependencies.

- Coverage reports only as a navigation aid to unexecuted code, not as proof of meaningful behavior.

## Decision rules

- If a pure function/invariant can be proved without infrastructure, write focused unit/property tests.

- If correctness depends on serialization, ORM, SQL, transaction or framework routing, use an integration test with the real component.

- If two independently deployed components share a contract, add producer/consumer or schema contract tests where they catch drift earlier than E2E.

- If a bug required a particular state sequence, encode that sequence as a regression scenario instead of asserting only the final helper function.

- If behavior depends on time, inject/freeze a clock instead of sleeping; if it depends on randomness, control the seed/source.

- If a mock asserts an internal call sequence but users only care about the resulting state/output, prefer asserting the outcome unless the interaction itself is contractual.

- If concurrency matters, coordinate competing operations deliberately and assert the invariant; looping a race thousands of times is weak evidence.

- If an E2E test is expensive/flaky, retain only cross-system journeys that cannot be proven credibly at lower layers.

## Workflow

1. Translate the change into claims: success behavior, invariants, forbidden outcomes, errors, compatibility and operational failure behavior.

2. Rank claims by impact and likelihood; identify which would be most expensive to discover after deployment.

3. Select test levels per claim and reuse the project's existing harness unless it cannot represent the risk.

4. For bug fixes, create a minimal failing regression before or alongside the fix and confirm it detects the previous behavior.

5. Implement boundary and failure-path tests before adding broad snapshots or coverage-only cases.

6. Make setup deterministic and data-local; remove hidden dependency on execution order or machine state.

7. Run targeted tests during development, then the canonical full quality suite required by the repository.

8. Review test quality after green: mutation of important inputs, failure diagnostics, brittleness and whether any mock bypasses the actual risk.

## Implementation patterns

- Table/parameterized tests are effective for validation matrices and compatibility cases when each row expresses a meaningful scenario.

- Property-based tests are valuable for parsers, serialization round-trips, arithmetic invariants and state machines with large input spaces.

- Golden/snapshot tests work for stable structured output when reviewed intentionally; avoid huge snapshots that hide semantic changes.

- Contract tests should validate schema plus semantics such as required headers, idempotency and error mapping where those matter.

- Test builders/factories should default to valid minimal entities and let a scenario override only relevant fields.

- Use fake external servers or recorded contract fixtures for deterministic protocol tests; reserve live vendor tests for separate opt-in smoke suites.

- For asynchronous jobs, test enqueue intent separately from worker behavior and test duplicate/retry semantics at the worker boundary.

- For migrations, test upgrade from representative old data and validate resulting constraints/data, not only migration importability.

## Failure modes

- Coverage theater: adding trivial getter tests raises percentage while risky branches remain untested. Re-rank tests around failure impact.

- Mock maze: every collaborator is mocked and the test only proves call wiring. Replace with a real boundary or assert meaningful state/output.

- Sleep-based async test: timing variance creates flakes. Wait on observable conditions or control the scheduler/clock.

- Shared mutable fixture: one test's order/state affects another. Use isolated transactions/resources and explicit setup.

- Snapshot blindness: a huge snapshot is updated wholesale after a change. Narrow it or use semantic assertions that require review.

- SQLite-for-Postgres proof: backend-specific constraints/locking are “tested” on a different engine. Run the real supported datastore.

- Happy-path-only API test: no validation/auth/error/concurrency cases. Add risk-based negatives rather than more success variants.

- Regression without reproduction: a new test passes before the bug fix. Tighten it until it demonstrates the failure being prevented.

## Verification

- Temporarily reverse or disable the key fix where practical and confirm the regression test fails for the intended reason.

- Run the narrow test file repeatedly/parallel if it introduces timing, shared resources or randomized generation.

- Run the project's canonical full test/quality command in the supported environment.

- Inspect skipped/xfail tests and ensure the changed capability is not accidentally excluded from CI.

- Check test runtime and fixture scope so a correct test does not make the suite operationally unusable.

- Review assertions for forbidden side effects, not only expected outputs.

- For integration tests, confirm they exercise the real parser/database/framework boundary rather than a fake with different semantics.

- For E2E journeys, verify diagnostics preserve enough context to locate which subsystem failed.

## Completion criteria

- Every material acceptance criterion or invariant has credible repeatable evidence at an appropriate test level.

- The regression suite would detect the specific defect class being changed, not merely execute nearby code.

- Failure, edge and concurrency cases are covered in proportion to their production risk.

- Tests are deterministic, isolated and diagnostic under the repository's CI parallelism/environment.

- Mocks/fakes do not bypass the behavior whose correctness is being claimed.

- The canonical project quality suite passes, and any unexecuted verification is explicitly reported.

- No test-only design compromises leak into production behavior without a clear boundary.

## Related skills and escalation

- Use `verification` to combine tests with static, runtime, visual and operational evidence.

- Use `database`, `webhooks`, `external-integrations` or framework skills for boundary-specific test patterns.

- Use `visual-qa` for rendered UI claims that unit/DOM assertions cannot prove.

- Escalate when the repository lacks a realistic environment to verify a high-risk migration, concurrency or external-contract change.
