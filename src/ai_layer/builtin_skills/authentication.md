---
slug: authentication
description: Authentication, credential, session, token, and identity lifecycle discipline.
kind: capability
keywords:
- authentication
- login
- session
- jwt
- oauth
- oidc
- password
- credential
- token
- authenticate
- logout
- session token
- refresh token
- sign in
- аутентиф
- вход
- пароль
- сессия
---
# Authentication Skill

## Apply when
Identity establishment, login/logout, credentials, sessions, access/refresh tokens, OAuth/OIDC, or password flows change.

## Mandatory rules
- Use established framework/provider primitives before custom protocols or cryptography.
- Store passwords only with a modern password-hashing primitive and project-approved parameters.
- Tokens/sessions need explicit issuer/audience/scope/expiry/revocation or rotation semantics appropriate to the mechanism.
- Never log credentials, raw tokens, password reset secrets, or bearer headers.
- Authentication proves identity; authorization still must validate the requested action/resource.

## Decision rules
- Prefer secure, httpOnly, same-site cookies for browser sessions when consistent with project architecture; do not switch token transport casually.
- Refresh/rotation flows must define replay and stolen-token behavior before implementation.
- Do not invent JWT/OAuth semantics that the provider/library already specifies.

## Failure modes
Long-lived unrevocable tokens, account enumeration, insecure reset flows, session fixation, secrets in URLs/logs, custom password hashing, and treating successful authentication as universal permission.

## Quality gates
- Invalid/expired/revoked credentials are rejected.
- Login/reset/session endpoints have abuse/rate controls where required by the project threat model.
- Security-sensitive behavior is tested at the actual authentication boundary.
