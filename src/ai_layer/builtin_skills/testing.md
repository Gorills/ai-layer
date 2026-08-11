---
slug: testing
description: Risk-proportional, evidence-based test selection and verification discipline.
kind: core
keywords:
- test
- testing
- pytest
- unit
- integration
- regression
- smoke
- verify
- coverage
- tests
- bug
- fix
- implement
- verification
- review
- flaky
- исправ
- тест
- баг
- провер
- реализац
---
# Testing Skill

## Apply when
Implementation, bug fixing, refactoring, review, or any behavior change needs evidence.

## Mandatory rules
- Test observable behavior and invariants, not implementation trivia.
- Start with the narrowest check that can falsify the change, then broaden according to risk.
- Use real integration tests for persistence/protocol/runtime boundaries that mocks cannot prove.
- A fixed bug gets a regression test when the failure can be reproduced deterministically.
- Never weaken an assertion or expected behavior only to make the suite pass.

## Decision rules
- Unit test pure logic; integration-test boundaries; end-to-end test only the cross-system behavior that needs it.
- Concurrency/auth/migration/security failures need negative or conflict-path coverage proportional to impact.
- If an environment prevents a required check, report it as unexecuted rather than inferring success.

## Failure modes
Mocking the logic under test, order-dependent fixtures, sleeps as synchronization, tests coupled to irrelevant internals, silently skipped integration coverage, and claiming commands passed without executing them.

## Quality gates
- Positive and relevant negative paths exist.
- Fixtures are deterministic, isolated, and bounded.
- Executed commands and outcomes are distinguishable from recommendations.
- Broader regression scope matches the blast radius of the change.
