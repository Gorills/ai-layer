---
slug: authorization
description: Server-side authorization and object/action scope enforcement.
kind: capability
keywords:
- authorization
- permission
- role
- policy
- acl
- rbac
- ownership
- tenant
- authorize
- owner
- non-owner
- admin
- access control
- права доступа
- авторизац
- роль
- разрешен
---
# Authorization Skill

## Apply when
Permissions, roles, ownership, tenant boundaries, privileged actions, or resource-level access are involved.

## Mandatory rules
- Enforce authorization on the trusted server/service boundary for every protected operation.
- Check both action and target resource; authenticated identity alone is insufficient.
- Default deny when scope is missing or ambiguous.
- Tenant/account/project identifiers from the request are claims to validate, not authority.
- Keep policy logic centralized in the project’s existing authorization mechanism rather than scattering ad-hoc role checks.

## Decision rules
- Prefer capability/policy checks over UI hiding or route-name assumptions.
- For object-level access, query or validate ownership/tenant scope as part of the protected operation.
- Privileged bypasses require an explicit, auditable project convention.

## Failure modes
IDOR/BOLA, horizontal or vertical privilege escalation, client-only guards, `is_admin` checks duplicated across handlers, authorization after a side effect, and tenant scope inferred from untrusted input.

## Quality gates
- Negative tests prove another user/tenant/role cannot perform the action.
- Privileged and ordinary paths are distinguishable in audit/logging where the project supports it.
- Any intentional exception to the normal policy is explicit and tested.
