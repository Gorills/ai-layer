---
slug: external-integrations
description: Third-party integration engineering for adapters, timeouts, retries, idempotency, rate limits, contract drift, observability and graceful degradation.
kind: capability
keywords:
- integration
- third party
- api client
- sdk
- retry
- timeout
- rate limit
- circuit breaker
- adapter
- vendor
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# External Integrations Skill

## Apply when

Use when calling an external HTTP/API/SDK service, exchanging data with a vendor, depending on remote availability, or mapping an external domain model into the application. This includes payments, CRM, messaging, maps, AI providers and internal services owned by another team.

## Core contract

- Treat every remote dependency as slow, fallible, independently changing and capable of returning malformed or semantically surprising data.

- Hide vendor-specific models/errors behind a narrow adapter boundary unless the product intentionally exposes that vendor contract.

- Define connect/read/total timeouts explicitly. A request without bounded time can exhaust worker/thread/connection capacity during vendor failure.

- Retries must be limited to operations and failures that are safe to repeat; mutating calls need vendor/application idempotency semantics first.

- Classify failures into validation/business rejection, authentication/configuration, rate limiting, transient availability and permanent contract errors.

- Honor rate-limit/retry signals where trustworthy, add bounded backoff/jitter and prevent synchronized retry storms.

- Persist local intent/state before unreliable remote work when the product must recover after process crashes or timeouts.

- Validate remote responses at the boundary and normalize to internal types; do not let missing/extra vendor fields crash unrelated layers.

- Expose integration health via structured outcome/latency/retry/rate-limit metrics without logging secrets or full sensitive payloads.

- Plan contract/version drift: pin SDKs where appropriate, read official changelogs, and keep contract fixtures/tests around behavior the app depends on.

## Evidence to inspect

- Current integration adapter/client and every direct vendor SDK/API call that may bypass it.

- Credentials/configuration, base URLs, environment selection, timeouts and proxy/network settings.

- Vendor request/response schemas, idempotency support, retry/rate-limit documentation and webhook counterparts.

- Local state machine/records that track remote operation identity and status.

- Error mapping, retry policy, queue worker configuration and dead-letter/manual recovery.

- Metrics/logs/incidents showing real latency, throttling, malformed responses or duplicate outcomes.

## Decision rules

- If the remote mutation may succeed but the response times out, reconcile/query by idempotency/business key before blindly retrying.

- If retries can duplicate a business effect, use provider idempotency keys or a locally persisted operation identity that maps to one remote effect.

- If transient failures should not block user request latency, enqueue durable work only when delayed completion is acceptable and product state represents pending status.

- If the vendor SDK leaks types across the codebase, wrap it in an adapter and translate to internal models/errors.

- If rate limits are shared globally, coordinate concurrency/backoff rather than letting each request retry independently.

- If an optional integration is down, degrade only the dependent capability; do not turn a noncritical vendor into global application unavailability.

- If a response field is undocumented/unstable, do not build critical logic on it without source/contract evidence.

- If credentials differ by tenant/account, bind selection to authoritative tenant configuration and prevent cross-tenant credential reuse.

## Workflow

1. Map the business operation, local source of truth and exact point where the external system becomes involved.

2. Read the provider's authoritative contract for the project's API/SDK version, especially idempotency, errors, timeouts and limits.

3. Define an adapter contract with normalized inputs/outputs and stable internal error categories.

4. Choose local durable state, operation identity, timeout and retry/reconciliation semantics.

5. Implement client calls with explicit bounds, safe authentication and response validation.

6. Add observability for outcome, provider code, latency, retries and throttling using redacted metadata.

7. Test success plus timeout-after-success, rate limit, malformed response, auth failure and duplicate/retry paths.

8. Provide operator/user recovery behavior for terminal or ambiguous outcomes.

## Implementation patterns

- Use one configured client/adapter construction path so timeout, authentication, headers and telemetry do not drift between calls.

- Map provider exceptions/statuses into a small internal taxonomy and preserve provider diagnostic IDs safely for support.

- Use durable operation records for externally important mutations, storing local key, provider key, state, attempt metadata and last safe error.

- For polling, cap cadence/duration and stop on terminal states; prefer provider webhooks when reliable and verified, with reconciliation as backup.

- For optional read-only enrichment, cache/fallback may be acceptable if staleness is explicit and sensitive data policy permits.

- For provider migrations, keep a provider-neutral application contract and switch adapters at composition/configuration boundaries.

- Use test servers/contract fixtures for deterministic CI; live-provider smoke tests belong in a separate controlled environment.

- When provider accepts client request IDs/idempotency keys, derive/store them from a stable local operation rather than regenerating per retry.

## Failure modes

- Infinite/default timeout: vendor outage consumes all workers. Configure bounded connect/read/total time.

- Retry-all policy: permanent 4xx/business errors hammer provider and delay terminal feedback. Classify failures.

- Timeout duplication: provider succeeded but client retries new request identity. Reuse operation identity and reconcile.

- SDK sprawl: business code imports provider models everywhere. Introduce adapter/translation boundary.

- Raw payload logs: credentials/PII leak during debugging. Redact and log only diagnostic identifiers/metadata.

- Rate-limit stampede: many workers retry simultaneously. Honor reset hints and use bounded jitter/concurrency control.

- Provider-as-truth ambiguity: local and remote state disagree with no ownership rule. Define authority/reconciliation.

- Optional dependency becomes global health failure: readiness checks fail app for noncritical vendor. Scope health semantics.

## Verification

- Run adapter contract tests for representative success/error/malformed payloads.

- Inject connect/read timeout, connection reset and rate-limit responses; verify bounded retries and final state.

- Simulate ambiguous timeout after remote success and confirm idempotent reconciliation prevents duplication.

- Verify credential/header/payload logging redaction and tenant/provider configuration selection.

- Exercise queue retry/dead-letter/manual recovery for asynchronous integrations.

- Check metrics/logs expose provider, operation, outcome, duration and retry count without secrets.

- Review official provider version docs/changelog for any behavior the implementation assumes.

- Confirm disabling/outage of optional integration degrades only intended features.

## Completion criteria

- Vendor details are contained behind an explicit adapter or intentionally documented public dependency.

- Timeout, retry, idempotency and ambiguous-outcome semantics are defined and tested.

- Remote response/errors are validated and normalized before reaching business logic.

- Rate limits and credentials have bounded, tenant-safe operational handling.

- Operators can diagnose and recover terminal/ambiguous states.

- Contract-drift risk is covered by pinned/source-backed behavior and focused tests.

## Related skills and escalation

- Use `webhooks` for inbound provider callbacks and `data-consistency` for local/remote state reconciliation.

- Use `security` for credential/SSRF/sensitive-data boundaries and `source-first` for provider-version facts.

- Use `backend` for durable use-case state and async worker orchestration.

- Escalate when the provider cannot offer idempotency/reconciliation for an irreversible high-value operation.
