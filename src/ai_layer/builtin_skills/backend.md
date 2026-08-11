---
slug: backend
description: Backend service and API implementation discipline across common server
  runtimes.
kind: domain
keywords:
- backend
- api
- service
- endpoint
- server
- handler
- controller
- request
- response
- route
- middleware
- worker
- payment
- бекенд
- апи
- эндпоинт
- сервер
- обработчик
---
# Backend Skill

## Apply when
The task changes server-side request handling, application services, API behavior, workers, or backend integrations.

## Mandatory rules
- Validate transport input at the edge; keep domain/application behavior outside transport handlers.
- Preserve existing error and response contracts unless the task explicitly changes them.
- Bound external I/O with appropriate timeout/cancellation behavior and bound user-controlled result sizes.
- Make transaction ownership explicit; do not keep transactions open across unrelated network calls unless the architecture requires it.
- Reuse existing dependency injection, service, repository, logging, and configuration conventions.

## Decision rules
- Thin handler + existing service seam is preferred over embedding orchestration in routes/controllers.
- Retries are allowed only for operations whose idempotency and failure semantics are understood.
- For a new public endpoint, define validation, authorization, error mapping, and compatibility before implementation.

## Failure modes
Duplicated business logic in handlers, unbounded pagination, swallowed exceptions, secret-bearing logs, blind retries, implicit global state, and introducing a second service pattern beside the existing one.

## Quality gates
- Positive and relevant failure paths are tested.
- Authorization is enforced server-side where applicable.
- External-call and DB failure behavior is deterministic enough to diagnose.
- Configured static checks/tests for the changed backend area actually run, or omissions are reported.
