---
slug: django
description: Django/DRF request, ORM/query, transaction, auth, migration, media/static
  and production deployment discipline.
kind: stack
keywords:
- django
- drf
- queryset
- model
- serializer
- viewset
- middleware
- media
- static
- migration
- django admin
- media_root
- static_root
- asgi
- wsgi
entry_sections:
- Apply when
- Core contract
---
# Django Skill

## Apply when
A Django/DRF project changes request handling, models/ORM, serializers/forms, authorization, admin, middleware, migrations, media/static, workers or deployment.

## Core contract
- Follow the project's actual Django/DRF architecture: model/view/service ownership, serializers/forms, permissions, settings modules and app boundaries. Do not introduce a new layer just because it is fashionable.
- Prevent N+1/query-per-row behavior from demonstrated access patterns; use `select_related`/`prefetch_related` deliberately.
- Use `transaction.atomic` around invariant-preserving DB units, not as a blanket wrapper around external HTTP/network work.
- Keep migrations compatible with historical models/data and deployment ordering; do not import current application models in migrations.
- Enforce permissions server-side at object/action boundaries.
- Treat `MEDIA_ROOT`/configured storage as user-data persistence and `STATIC_ROOT` as deployment/build output according to the actual project.

## ORM and queries
Understand queryset laziness/evaluation before changing loops/serializers. Prefer set/bulk/database operations where semantics are equivalent and row counts justify them. Use `exists`, aggregates, annotations and constraints intentionally; do not micro-optimize without query evidence.

## Transactions and side effects
Keep durable state transitions atomic when multiple writes form one invariant. External APIs, email and queues should not be casually invoked inside a long transaction. If side effects depend on commit, use the project's established post-commit/outbox/task pattern rather than inventing a second flow.

## Validation and authorization
Place invariant validation in the owning layer. Serializer/form validation is appropriate for request shape; database constraints protect durable uniqueness/invariants; domain rules should not be duplicated inconsistently across serializers/views/models. CSRF/session/auth primitives are preferred; exemptions need a concrete verified boundary such as signed webhooks.

## Migrations
For risky production changes prefer compatible sequences: add nullable/new structure, deploy compatible code, backfill in bounded form, then enforce constraints/remove old paths when safe. Data migrations must use historical apps/models. Do not assume rollback can restore deleted/transformed data.

## Media, static and deployment
In Docker/local/prod changes, distinguish source code, static collection/build artifacts and user media. Development `runserver` behavior is not production server behavior. Account for WSGI/ASGI server, workers, migrations, static/media serving/storage, health and `check --deploy` or equivalent project checks.

## DRF/API performance
Trace serializer relationship access, pagination and permissions on list/detail paths. Object permission logic must also be enforced for custom actions/querysets where framework defaults do not cover it.

## Quality gate
Run relevant Django checks/tests/migration checks and real ORM integration. For query changes inspect query count/shape where practical; for deployment/storage changes verify the actual configured settings/path behavior.
