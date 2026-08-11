---
slug: documentation
description: Documentation-impact discipline that updates real project contracts without
  creating README churn for internal changes.
kind: capability
keywords:
- documentation
- docs
- readme
- runbook
- deployment
- configuration
- env example
- api docs
- config
- env
- docker
- api
- endpoint
- storage
- migration
- install
- startup
entry_sections:
- Apply when
- Core contract
---
# Documentation Skill

## Apply when
A change modifies a user/developer/operator-visible contract: setup, configuration, environment variables, public API, deployment, persistent storage, migrations, runtime processes or operational recovery.

## Core contract
- First inspect the scanner's documentation map and update the document that already owns the affected contract; do not create a second competing guide.
- Documentation is impact-driven. An internal bugfix with no documented contract change should not churn README files merely to satisfy a ritual.
- New/changed environment variables require the project's safe example/config reference when one exists; never copy real secrets.
- Deployment/runtime/storage changes require operator-facing instructions when operators must act differently.
- Public API/schema behavior must remain aligned with generated/manual API documentation owned by the project.

## Impact map
Configuration contract -> config docs and `.env.example`/equivalent. Local startup -> README/dev guide. Deployment/process topology -> deployment/runbook. Persistent storage/media -> ops/deployment/backup guidance. Public API -> OpenAPI/API docs/examples. Data migration requiring operator action -> upgrade/runbook. Architectural decision -> ADR/architecture docs only when the project actually maintains them.

## Quality
Write commands/paths/names that exist in the current tree. Separate required steps from optional recommendations. State destructive/irreversible operations clearly. Do not document a behavior that was not implemented or verified.

## Review gate
Reviewer checks documentation impact against the actual diff. If impact exists and the owning docs/examples are stale or missing, that is an actionable finding; if no external contract changed, no doc change is required.
