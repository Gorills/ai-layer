---
slug: security
description: Trust-boundary security discipline covering validation, auth, secrets,
  web/API/file risks and secure failure behavior.
kind: core
keywords:
- security
- trust
- secret
- token
- injection
- vulnerability
- permission
- csrf
- cors
- signature
- xss
- ssrf
- auth
- webhook
- upload
- file path
- credential
- privilege
- payment
- oauth
- безопасность
- авторизац
- аутентиф
- секрет
- токен
- права
entry_sections:
- Apply when
- Core contract
---
# Security Skill

## Apply when
The task crosses a trust boundary or touches identity, permissions, secrets, untrusted input, files, webhooks, public APIs, privileged operations, sensitive data, external integrations or deployment exposure.

## Core contract
- Identify actor, untrusted entry point, protected asset, authorization decision and enforcement boundary before changing controls.
- Authentication and authorization are separate. Authorize the specific action/resource server-side; never trust UI/client checks.
- Validate untrusted data at the trusted boundary for structure, type, size and allowed values; then encode/parameterize for the destination sink.
- Prefer framework/platform security primitives over custom crypto, session/token, CSRF/CORS or signature schemes.
- Deny safely on ambiguous authorization or invalid security state; do not add permissive fallback paths for availability.
- Positive tests are insufficient: security-sensitive changes need relevant negative/abuse-path verification.

## Input and output boundaries
Prevent SQL/command/template/path/header injection with destination-appropriate APIs. Escaping is context-specific; one generic sanitizer is not a security architecture. Treat filenames, archive members, URLs, redirects and webhook payloads as hostile until validated.

## Web and browser
Preserve framework CSRF protections for cookie/session-authenticated state changes. CORS is a browser cross-origin policy, not authentication. Prevent XSS through contextual output handling and avoid rendering unsanitized trusted-looking HTML. Security headers/CSP should match the application's real asset/runtime requirements rather than copied maximal policies that break production.

## API and authorization
Check object/tenant ownership at the server-side resource boundary. Avoid mass assignment of fields the caller must not control. Return only data needed by the caller and avoid exposing internal identifiers/secrets unnecessarily. Rate/abuse controls belong near expensive or sensitive public operations when the product requires them.

## Secrets and credentials
Never store or print real secrets in source, examples, logs, screenshots, test fixtures or frontend bundles. Use least-privilege credentials and separate environments. Error messages may identify the failing subsystem but must not echo tokens, connection strings or sensitive payloads.

## Files and SSRF
For uploads, constrain size/type/name and store outside executable code paths as appropriate. Resolve archive/path extraction safely against the intended root. For server-side URL fetching, constrain protocols/targets and do not let user input reach internal metadata/admin networks without explicit policy.

## Cryptography
Use maintained platform libraries and established algorithms/modes. Do not invent hashing/encryption/signature constructions. Password storage, token generation and key handling must use framework/security-library primitives with appropriate randomness and lifecycle.

## Failure behavior
Security checks must fail closed without turning normal operational faults into data corruption or irreversible lockout. Log enough for diagnosis but not secret-bearing request bodies/credentials. State residual assumptions explicitly when external enforcement cannot be verified.

## Quality gate
Verify enforcement at the actual trusted boundary, including a prohibited path. Confirm secrets are absent from code/logs/client artifacts. Run the project security/static/dependency checks that are already configured and report unavailable verification honestly.
