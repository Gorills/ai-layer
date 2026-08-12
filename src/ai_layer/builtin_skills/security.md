---
slug: security
description: Threat-driven application security for trust boundaries, input handling, secrets, cryptography, abuse resistance and secure verification.
kind: core
keywords:
- security
- threat model
- injection
- secrets
- cryptography
- ssrf
- xss
- csrf
- abuse
- hardening
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Application Security Skill

## Apply when

Use whenever untrusted input, authentication, authorization, secrets, uploads, external URLs, code execution, sensitive data, payment-like workflows or security controls are touched. Also use when adding a new network boundary, privileged background process, dependency or administrative operation.

## Core contract

- Start with assets, actors, trust boundaries and abuse cases. A security checklist without a threat model misses the risks unique to the feature.

- Treat every external value as untrusted until validated for its semantic purpose; escaping, parameterization and authorization are separate controls.

- Minimize privilege and exposure by default: narrow credentials, narrow filesystem/network access, narrow data selection and deny-by-default authorization.

- Never invent cryptographic primitives, password hashing formats, token signing schemes or secret-storage mechanisms when maintained platform primitives exist.

- Authentication proves an identity/session claim; authorization decides whether that identity may perform this exact action on this exact resource. Enforce both server-side.

- Secrets must not enter source control, logs, URLs, client bundles or exception text. Design rotation and revocation before a credential becomes operationally critical.

- Security controls must fail closed for ambiguous or malformed input while preserving availability against cheap abuse where possible.

- Normalize before security decisions when multiple encodings, paths, hostnames or identifiers could represent the same object.

- Assume attackers can replay, reorder, race and automate requests; model idempotency, CSRF, rate/abuse controls and concurrency accordingly.

- Verification must include negative/adversarial cases. A happy-path login or upload test is not security evidence.

## Evidence to inspect

- Trust boundaries: public endpoints, admin surfaces, internal services, workers, webhooks, file/object storage and outbound network access.

- Authentication/session/token configuration, authorization policies and resource ownership checks.

- Input validation, query construction, template rendering, command/process execution and filesystem path handling.

- Secret sources, environment/configuration, logging/redaction and credential rotation paths.

- Dependency manifests and security-sensitive libraries such as crypto, parsers, serializers and upload processors.

- Deployment/runtime permissions, container user, network egress, CORS/CSRF/security headers and proxy assumptions.

## Decision rules

- If user-controlled data reaches SQL/NoSQL/query syntax, use parameterized/query-builder APIs and still validate semantic constraints.

- If user-controlled content reaches HTML/JS/CSS/URL contexts, use context-appropriate encoding/safe templating; do not disable escaping to make rendering convenient.

- If the application fetches user-supplied URLs, enforce an SSRF policy including schemes, DNS/IP resolution, redirects and private/link-local destinations.

- If a file path includes user input, resolve against an allowed root and reject traversal/symlink escapes; validating only `..` text is insufficient.

- If a privileged action is browser cookie-authenticated, evaluate CSRF even when CORS is configured; CORS is not a CSRF defense.

- If a token/credential is long-lived, define storage, audience/scope, expiration, rotation, revocation and compromise response.

- If resource access is based on an identifier from the request, authorize ownership/permission after resolving the resource; do not rely on identifier unpredictability.

- If a new error path includes raw payloads or headers, redact secrets and sensitive fields before logging.

## Workflow

1. Describe the feature's assets, entry points, privileged effects and trust boundaries in a compact threat model.

2. List realistic attacker capabilities and abuse cases: forged identity, cross-tenant access, injection, replay, resource exhaustion, data exfiltration and privilege escalation.

3. Map each abuse case to preventive, detective and recovery controls already present in the codebase.

4. Implement validation and authorization closest to the authoritative operation, then add transport-level defenses as defense in depth.

5. Use standard framework/platform primitives for sessions, cryptography, password hashing, secret loading and safe serialization.

6. Add rate/size/time bounds to attacker-controlled expensive operations and asynchronous work.

7. Instrument denied/abusive outcomes without logging sensitive payloads; ensure operators can distinguish attack-like traffic from system faults.

8. Test adversarial inputs and run the project's static/dependency/security checks before release.

## Implementation patterns

- Centralize policy decisions in explicit authorization functions/policies while passing the resource and action, not merely a role string.

- Represent secrets with dedicated configuration paths and redaction-aware logging; never make generic object `repr` expose them.

- Use allowlists for protocols, file types, redirect targets or executable actions when the valid set is actually bounded.

- Use signed, expiring, purpose/audience-bound tokens for temporary capabilities; reject reuse when single-use semantics matter.

- For uploads, separate metadata validation from content handling, generate server-side names, store outside executable roots and serve with safe content disposition/type.

- For outbound calls, configure connect/read/total timeouts and response-size bounds in addition to destination policy.

- For admin/maintenance operations, require stronger authorization and record auditable actor/action/target/outcome without recording secrets.

- For sensitive comparisons or crypto verification, use library APIs designed for the primitive rather than home-grown string comparison.

## Failure modes

- Role-only authorization: `is_admin` or broad role checks replace resource/action policy and create cross-tenant access. Authorize the actual target.

- Validation-as-sanitization: input is regex-cleaned then concatenated into a dangerous context. Use safe APIs plus semantic validation.

- Secret in logs: debugging dumps headers/config/environment. Redact at structured logging boundaries and add regression tests.

- SSRF hostname check: code rejects `localhost` text but follows redirects or resolves to private IPs. Validate the full request resolution policy.

- Path traversal substring check: encoded or symlink paths escape. Resolve canonical paths beneath an allowed root and control symlinks.

- Custom crypto/token format: convenient signing/encryption omits key rotation, nonce/audience or misuse resistance. Adopt maintained standard primitives.

- CORS misconception: permissive or restrictive CORS is treated as access control. Keep server authorization and CSRF controls independent.

- Security by hidden identifiers: UUID/unlisted routes are assumed protected. Enforce authorization for every resource operation.

## Verification

- Create negative tests for unauthenticated, wrong-user, wrong-role/permission and cross-tenant access to each sensitive operation.

- Fuzz or enumerate malformed boundary inputs, oversized values and ambiguous encodings that could alter parsing or normalization.

- Test injection-sensitive sinks with payloads that would break unsafe concatenation while confirming parameterized/safe APIs are used.

- Test token/session expiration, revocation/rotation and replay semantics relevant to the feature.

- Exercise upload/path/URL redirects and symlink/private-network cases when those surfaces exist.

- Inspect logs and error responses during failures for credentials, tokens, PII and internal stack/config disclosure.

- Run dependency/static/security scanners configured by the project and triage findings rather than suppressing them generically.

- Verify runtime least privilege and secret sourcing in the deployment configuration, not only local development.

## Completion criteria

- A threat model identifies the assets, trust boundaries and material abuse cases introduced or changed.

- Authentication and authorization are independently enforced at the authoritative operation.

- Dangerous sinks use safe platform primitives, and untrusted inputs are semantically validated and bounded.

- Secrets, tokens and sensitive data have explicit storage, logging, lifecycle and compromise behavior.

- Negative/adversarial tests cover the highest-risk abuse cases and are part of repeatable verification.

- Operational controls can detect and investigate abuse without creating a secondary data leak.

- Any accepted security risk is explicit, scoped and owned rather than hidden in a TODO.

## Related skills and escalation

- Use `authentication` and `authorization` for deeper identity/session and policy mechanics.

- Use `file-handling`, `webhooks`, `external-integrations` and `api-contracts` for specialized attack surfaces.

- Use `source-first` for version-sensitive framework security behavior; prefer official security documentation.

- Escalate immediately when the change affects cryptography, credential recovery, tenant isolation, payment authorization or remote code execution boundaries.
