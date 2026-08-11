---
slug: docker
description: Environment-aware Docker/Compose engineering for local development, tests,
  production deployment, persistence, mounts, health and safe upgrades.
kind: stack
keywords:
- docker
- compose
- container
- image
- volume
- mount
- deployment
- devcontainer
- bind mount
- deploy
- dockerfile
- postgres data
- media volume
- hot reload
entry_sections:
- Apply when
- Core contract
---
# Docker Skill

## Apply when
Dockerfiles, Compose services, local/test/prod environments, persistent data, deployment, workers, health checks, or containerized developer workflows change.

## Core contract
- Read the scanner-provided Docker/runtime/data topology before editing. Preserve the project's existing service names and environment split unless the task explicitly redesigns them.
- Separate concerns: application code, runtime dependencies, database data, user media/uploads, generated static/build output, cache/temp data, and secrets are different persistence classes.
- Local development may bind-mount source for immediate code pickup; production code should normally come from an immutable image, not a host source mount.
- Database and user-generated media must survive container recreation through named/external volumes or external managed storage. Never hide persistent data inside an ephemeral container layer.
- Test services and databases must be isolated from development/production data.
- Deployment changes are incomplete until startup, migrations, health, rollback/data compatibility, and documentation impact are considered.

## Local development
Use bind mounts for source only where live code pickup is intended. Avoid masking image-owned dependency directories such as `.venv`, `vendor`, or `node_modules`; use container/named volumes or an architecture consistent with the project. Preserve host/container UID/GID usability where generated files cross the boundary. Keep dev-only ports, debuggers, reloaders, and permissive settings out of production configuration.

## Test environment
Use deterministic disposable application state and an isolated database/schema/volume. Do not point tests at developer or production persistence. Prefer Compose profiles/override files only when they fit the existing project. Tests that require services should have readiness/health semantics rather than arbitrary sleeps.

## Production
Use multi-stage builds when they materially reduce build/runtime coupling. Copy only required runtime artifacts, run as a non-root user where practical, keep the build context small with `.dockerignore`, and avoid embedding secrets in layers or build args that persist. Use the framework's production server/process model, explicit workers, graceful termination, health checks, and bounded restart behavior.

## Persistence and media
Classify every writable path. Database directories and user media are persistent; caches and temporary artifacts are usually disposable. Static assets may be build output or persistent only if the application actually generates them at runtime. For Django inspect `MEDIA_ROOT`/`STATIC_ROOT`; for Laravel inspect configured filesystem disks and `storage/app` conventions. Never infer that `/data` is safe merely because it exists.

## Migrations and deployment ordering
Do not make destructive schema assumptions across rolling/recreated containers. Determine whether old and new application versions may overlap. Prefer backward-compatible migration sequences when zero/low-downtime deployment matters. Startup scripts must fail loudly on migration/configuration failure instead of starting a half-valid service.

## Compose discipline
Keep common service definitions shared and environment-specific differences explicit. Do not duplicate complete Compose files when an override/profile is sufficient and already conventional. `depends_on` is not application readiness by itself; use service health/readiness where the dependent process needs it.

## Verification
Verify build, container startup, service readiness, persistence across container recreation, isolated test data, expected live-source behavior in development, and production configuration without source bind mounts. Report Docker/host constraints that were not actually exercised.
