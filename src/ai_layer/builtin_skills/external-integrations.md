---
slug: external-integrations
description: Third-party API/provider integration boundary and failure-semantics discipline.
kind: capability
keywords:
- integration
- provider
- third-party
- sdk
- external api
- client
- timeout
- third party
- api client
- rate limit
- payment provider
- email provider
- интеграц
- провайдер
- внешний api
---
# External Integrations Skill

## Apply when
The code calls or adapts a third-party service, SDK, provider, remote API, or externally controlled protocol.

## Mandatory rules
- Put provider-specific details behind the project’s existing integration boundary; do not leak them through domain callers unnecessarily.
- Bound network calls with timeouts/cancellation and classify retryable vs terminal failures.
- Keep credentials/configuration outside source and never log secret-bearing request/response data.
- Preserve public/domain contracts when adding a provider unless the task explicitly changes them.

## Decision rules
- Extend an existing provider registry/adapter before creating a parallel flow.
- Retry only operations known to be safe/idempotent; honor provider rate-limit semantics.
- Normalize provider errors only as far as callers need; retain enough diagnostics for operations without leaking secrets.

## Failure modes
SDK calls scattered through business logic, infinite/default-long timeouts, blind retries, provider IDs conflated with internal IDs, undocumented sandbox/production behavior, and tests that only mock the happy path.

## Quality gates
- Success, timeout/provider failure, malformed response, and relevant retry behavior are covered.
- A real sandbox/contract test is used when the provider contract is consequential and available.
- Configuration and provider selection are deterministic and documented by current project conventions.
