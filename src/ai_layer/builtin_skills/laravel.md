---
slug: laravel
description: Laravel-specific request, Eloquent, queue, filesystem, configuration,
  migration and deployment discipline.
kind: stack
keywords:
- laravel
- eloquent
- artisan
- middleware
- form request
- queue
- horizon
- blade
- policy
- gate
- migration
- filesystem disk
entry_sections:
- Apply when
- Core contract
---
# Laravel Skill

## Apply when
A Laravel application's HTTP lifecycle, Eloquent models, validation, authorization, jobs/queues, events, filesystem, configuration, migrations or deployment changes.

## Core contract
- Detect and follow the project's Laravel/PHP version and existing conventions; do not modernize architecture incidentally.
- Keep validation, authorization and business invariants at their owning server-side boundaries. UI checks are not authorization.
- Treat Eloquent relationships/query loading as observable performance behavior; prevent query-per-row/N+1 regressions.
- Keep user files on configured filesystem disks and durable storage. Do not persist uploads only in an ephemeral container filesystem.
- Queue jobs are separate runtime processes: deployment, restart, retry/idempotency and configuration changes must account for workers.

## HTTP and application structure
Reuse existing controllers, Form Requests, services/actions, middleware, policies/gates and resources rather than adding a second architectural convention. Thin controllers are useful only when the project already has a clear ownership layer; do not introduce service classes mechanically.

## Eloquent and transactions
Use eager loading from demonstrated access patterns. Keep multi-write invariants transactional where appropriate, but do not hold database transactions open across slow external network calls without an explicit design. Use database constraints for durable invariants when safe and handle expected conflicts narrowly.

## Queues, events and scheduler
Jobs must be retry-aware and idempotent where retries can repeat side effects. Determine timeout, attempts/backoff and failed-job behavior for consequential work. Deployment must restart long-running queue workers when code/config requires it. Avoid hiding core synchronous business flow in events simply to decouple files.

## Filesystem and media
Inspect `config/filesystems.php`, disk configuration and existing storage conventions. Distinguish public user media from caches/build output. Ensure containers mount or externalize durable storage correctly and that URL generation/access control matches the chosen disk.

## Migrations
Keep deploy compatibility in mind: additive/nullable changes, backfills and later constraints are safer than one destructive step when old/new code may overlap. Do not assume rollback can undo data loss. Large backfills should be operationally bounded.

## Configuration and deployment
Configuration is typically cached in production; code must not call environment variables from arbitrary application locations when the project uses config indirection. Deployment changes must consider cache rebuilds, queue workers, scheduler, migrations, storage permissions and health checks.

## Verification
Run relevant application tests, migration/status checks and production-oriented configuration/build commands where available. Exercise Eloquent behavior against the real test database for transaction/query changes.
