---
slug: authentication
description: Authentication engineering for identity proof, sessions, tokens, password flows, MFA, rotation, revocation and account-recovery security.
kind: capability
keywords:
- authentication
- login
- session
- token
- jwt
- oauth
- password
- mfa
- recovery
- logout
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Authentication Skill

## Apply when

Use for login/logout, sessions, access/refresh tokens, password credentials, OAuth/OIDC integration, MFA, account recovery, remember-me behavior and any code that establishes or refreshes an authenticated principal.

## Core contract

- Authentication establishes who or what is acting; keep it separate from authorization decisions about what that principal may do.

- Prefer mature framework/identity-provider primitives for password hashing, session handling and protocol validation. Do not invent token/crypto formats.

- Model credential and session lifecycle: issue, bind to subject/client context, expire, rotate, revoke and recover after compromise.

- Server-side cookie sessions require secure cookie attributes and CSRF consideration; bearer tokens require safe storage, audience/scope and replay-aware lifecycle.

- Password storage must use a maintained adaptive password-hashing primitive with per-password salt and upgrade path; never reversible encryption or fast general-purpose hashes.

- Account discovery, reset and MFA flows must avoid giving attackers a cheaper identity-enumeration or account-takeover route than login itself.

- Logout semantics must match architecture: deleting a client token is not revocation if the token remains valid server-side.

- Authenticate each channel at its boundary; background/service credentials need distinct identities/scopes rather than sharing end-user secrets.

- Rate/abuse controls must protect expensive proof operations without becoming the only security barrier.

- Log authentication outcomes and session identifiers safely; never log raw passwords, bearer tokens, reset codes or secret authenticators.

## Evidence to inspect

- Framework auth/session configuration, cookie flags, token issuance/verification code and identity-provider settings.

- Credential tables/models, password hasher configuration and migration/rehash behavior.

- Login, logout, refresh, reset, email/phone verification and MFA endpoints.

- Client storage/transmission of credentials and CSRF/CORS assumptions.

- Revocation/session-store strategy, device/session listing and compromise response.

- Tests for expiration, replay, invalid signatures/claims, account state and recovery edge cases.

## Decision rules

- If browser authentication can use an HttpOnly secure session cookie, prefer that over exposing long-lived bearer tokens to JavaScript unless architecture requires otherwise.

- If tokens are used across services, validate issuer, audience, expiry and required claims with a maintained library; signature validity alone is not sufficient context validation.

- If refresh tokens exist, define rotation/reuse detection or another compromise model rather than treating them as immortal access tokens.

- If a password hash policy changes, rehash on successful authentication or run a controlled migration without ever needing plaintext passwords.

- If logout/revocation must invalidate active credentials immediately, choose stateful revocation/session storage accordingly.

- If reset links/codes grant account control, make them purpose-bound, expiring, single-use when practical and invalidate relevant old sessions after successful recovery.

- If responses differ for unknown versus known account in a public recovery/login flow, assess account-enumeration risk.

- If service-to-service authentication is added, use dedicated machine identity and least privilege instead of reusing a human/admin credential.

## Workflow

1. Map all ways a principal can become authenticated or regain access, including normal login, refresh, recovery, invitations and federation.

2. Define principal/session/token state and lifecycle, including disabled/deleted account behavior.

3. Select supported framework/provider primitives based on the project's threat model and client topology.

4. Implement verification and issuance at one authoritative boundary; normalize identity claims to an internal principal model.

5. Add secure storage/cookie configuration, expiration, rotation/revocation and abuse controls.

6. Implement recovery/logout/session-management semantics consistent with the chosen statefulness.

7. Test invalid, expired, revoked, replayed and wrong-audience/context credentials as well as successful login.

8. Inspect logs, client storage and network behavior to confirm secrets do not leak.

## Implementation patterns

- Use opaque server-side sessions when central revocation and simple browser security are valuable; use signed tokens when distributed verification is genuinely needed.

- Keep short-lived access credentials and longer-lived refresh/recovery capabilities distinct in purpose and protection.

- Bind reset/verification tokens to a single purpose and subject; store a hash/digest server-side when possession of database contents should not reveal usable tokens.

- Represent authentication state changes explicitly so disabling an account can terminate or reject future session use.

- For federation, validate state/nonce/redirect configuration and provider claims through the protocol library, then map to local identity ownership rules.

- MFA enrollment, challenge and recovery codes are separate privileged workflows; protect enrollment/change operations with recent authentication where appropriate.

- Use constant-behavior/error messaging where practical for public account lookup paths without creating poor diagnostics internally.

- Rotate secret keys/credentials with overlapping validation only for a bounded transition window.

## Failure modes

- Authz-in-login: login code assigns broad permissions without resource policy. Separate identity establishment from authorization.

- JWT signature-only validation: issuer/audience/expiry/context ignored. Validate required claims and key lifecycle.

- Token in localStorage by reflex: XSS gains long-lived credentials. Choose storage based on client architecture and threat model.

- Password reset backdoor: weaker recovery bypasses MFA/account protections. Threat-model recovery as authentication.

- Fake logout: UI deletes token but server still accepts it despite immediate revocation requirement. Align semantics.

- Raw token logging: middleware dumps Authorization/cookies/reset URLs. Redact at ingress and error logging.

- Shared machine/admin credential: compromise has excessive blast radius. Issue scoped service identities.

- Timing/message enumeration: public flows disclose account existence unnecessarily. Normalize response while retaining internal diagnostics.

## Verification

- Test login for valid/invalid credentials, disabled/locked/deleted account states and credential-policy edge cases.

- Test session/token expiry, malformed/signature failure, wrong issuer/audience and revoked state.

- Test refresh rotation/replay and concurrent refresh behavior if refresh credentials exist.

- Test logout/revocation using the same credential again according to the promised semantics.

- Test reset/verification codes for expiry, reuse, wrong purpose/subject and session invalidation behavior.

- Inspect browser cookie/storage/security attributes and verify CSRF defenses for cookie-authenticated mutations.

- Inspect logs/errors/traces for credential leakage.

- Run framework/provider security tests and current official guidance for version-specific behavior.

## Completion criteria

- All authentication entry/recovery paths share an explicit principal and credential lifecycle.

- Credential verification uses maintained standard primitives with correct context/claim validation.

- Expiration, rotation, revocation and compromise behavior match product requirements.

- Browser/client credential storage and CSRF/replay assumptions are deliberate.

- Recovery and logout cannot silently weaken the primary authentication model.

- Negative lifecycle/security tests and leak inspection provide evidence.

## Related skills and escalation

- Use `authorization` after identity is established and `security` for broader threat modeling.

- Use `api-contracts` for external auth endpoint behavior and `compatibility` for session/token migrations.

- Use `source-first` for OAuth/OIDC/framework version details rather than relying on memory.

- Escalate authentication protocol/cryptographic deviations from maintained standards.
