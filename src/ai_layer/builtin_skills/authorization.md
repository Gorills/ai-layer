---
slug: authorization
description: Authorization policy engineering for action-resource decisions, tenant isolation, least privilege, ownership and privilege-change verification.
kind: capability
keywords:
- authorization
- permission
- rbac
- abac
- policy
- tenant
- ownership
- least privilege
- admin
- access control
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# Authorization Skill

## Apply when

Use when adding or changing permissions, roles, ownership, tenant boundaries, admin operations, resource sharing or any server operation whose availability depends on the acting principal and target resource.

## Core contract

- Authorization answers whether this principal may perform this action on this resource in the current context; do not reduce the question to authentication or identifier secrecy.

- Enforce policy server-side at the authoritative operation so every transport/worker path cannot accidentally bypass it.

- Default deny. Grant the narrowest capability needed and make privileged exceptions explicit and reviewable.

- Resolve the target resource before checking ownership/tenant policy when policy depends on the resource; request-supplied owner/tenant claims are not authoritative.

- Tenant isolation is an invariant across reads, writes, searches, aggregates, exports, background jobs and caches—not just detail endpoints.

- Separate policy from presentation. Hiding a button improves UX but does not enforce access.

- Role-based rules may be an input to policy, but ownership, resource state, relationship and action frequently matter too.

- Privilege changes are security-sensitive mutations: authorize the grantor, constrain grantable privileges and audit actor/target/change.

- Prevent confused-deputy behavior in service/background actions by propagating or deliberately replacing actor context with a scoped machine identity.

- Test denied cross-tenant/resource cases systematically; same-tenant happy-path tests do not prove isolation.

## Evidence to inspect

- Policy/permission functions, middleware/decorators and where they are invoked relative to resource loading.

- Resource ownership/tenant fields and database query scoping.

- Roles/permissions storage and mutation endpoints/admin workflows.

- List/search/export/report queries and caches that can leak data across policy boundaries.

- Workers/system tasks and whether they preserve actor/tenant scope.

- Existing negative access tests and audit logging for privileged operations.

## Decision rules

- If authorization depends on resource state/ownership, pass the actual loaded resource or authoritative identifiers to policy rather than trusting client claims.

- If every query must be tenant-scoped, centralize/enforce the scope at repository/query boundaries and still test escape paths.

- If an admin override exists, define exactly which actions/resources it bypasses; avoid a universal `is_admin` shortcut unless intentionally required.

- If users can grant permissions, ensure they cannot grant privileges they do not own or elevate themselves through transitive roles.

- If a background job acts on behalf of a user, capture the necessary authorization context or re-authorize against current state depending on product semantics.

- If access is time/state dependent, decide whether authorization is evaluated at request, enqueue, execution or all relevant points.

- If denial would reveal existence of a sensitive resource, choose not-found/forbidden response semantics consistently without weakening server checks.

- If policy becomes complex, use named policy decisions with tests rather than scattered boolean expressions.

## Workflow

1. Enumerate actions and resource types touched by the feature, including list/export/bulk/background paths.

2. For each action, identify authoritative subject, resource, tenant and contextual attributes.

3. Write allow/deny rules and precedence explicitly, including admin/system exceptions.

4. Implement policy at the use-case/repository boundary and ensure transport helpers delegate rather than duplicate rules.

5. Scope queries before data leaves persistence when large collections or tenant isolation are involved.

6. Instrument sensitive privilege changes/denials appropriately without leaking confidential resource data.

7. Add matrix tests for roles/relationships/tenants and cross-boundary denial cases.

8. Search alternate entry points to ensure none bypass the canonical policy.

## Implementation patterns

- Use policy functions such as `can_update(actor, resource)` or structured policy objects that receive explicit context and return a decision/reason.

- Use tenant-scoped repository methods/query filters as a strong default and avoid raw unscoped access outside narrow administrative infrastructure.

- Model permissions as capabilities/actions rather than UI page names when the same operation exists through API/CLI/worker.

- For object sharing, store explicit relationship/grant records with owner/grantor/recipient/scope/lifecycle rather than overloaded role strings.

- For privileged support/admin access, require auditable intent and bounded scope when the product's risk warrants it.

- Cache authorization carefully: include subject/resource/policy version/tenant in keys and define invalidation on privilege changes.

- Use database row-level security only when operationally understood and tested; it complements, not excuses, application policy clarity.

- Return stable policy-denied errors to transports while keeping detailed internal audit reason safe.

## Failure modes

- UI-only permission: hidden button but endpoint is callable. Enforce at server use case.

- IDOR: resource ID is accepted and modified without ownership/tenant policy. Load and authorize target.

- Tenant filter omission: detail paths are scoped but search/export leaks other tenants. Enforce query boundary and matrix tests.

- Role soup: scattered string comparisons produce contradictory behavior. Centralize named policy decisions.

- Super-admin shortcut spread: many code paths bypass all checks. Constrain privileged override centrally.

- Grant escalation: manager can assign a role stronger than their own. Add grantability policy.

- Stale permission cache: revoked access remains valid. Define invalidation/versioning.

- Worker bypass: background task runs as unrestricted system for user-triggered operation. Preserve/re-evaluate scope.

## Verification

- Test unauthenticated, authenticated-no-permission, wrong-owner and wrong-tenant access for every sensitive action.

- Test list/search/export/bulk endpoints for cross-tenant leakage, not only single-resource fetches.

- Test role/permission grant and revoke, including attempts to self-escalate or grant stronger privilege.

- Test state-dependent policy transitions and cache invalidation if policy is cached.

- Exercise alternate transports/background execution that reach the same use case.

- Inspect database queries for missing tenant/resource filters in sensitive collections.

- Verify denial responses and logs do not leak secrets while audit data identifies actor/action/target safely.

- Run security review for any universal admin/system bypass.

## Completion criteria

- Every protected operation has one authoritative policy decision with explicit subject/action/resource/context.

- Tenant/ownership boundaries apply consistently across individual and collection operations.

- Privilege grants/revocations are constrained and auditable.

- Alternate transports/workers cannot bypass policy accidentally.

- Negative authorization matrix tests demonstrate isolation.

- Any privileged bypass is deliberately scoped, documented and reviewed.

## Related skills and escalation

- Use `authentication` for principal establishment and `security` for broader threat modeling.

- Use `database` for tenant-safe query structure and `api-contracts` for denial/error semantics.

- Use `testing` to build policy matrices and concurrency tests for privilege changes.

- Escalate when authorization policy is ambiguous at product/domain level rather than guessing permissions.
