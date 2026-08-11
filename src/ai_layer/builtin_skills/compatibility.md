---
slug: compatibility
description: Backward compatibility and upgrade-safe change discipline.
kind: capability
keywords:
- compatibility
- backward
- upgrade
- deprecation
- public api
- format
- migration
- backward compatibility
- downgrade
- deprecate
- existing clients
- file format
- config format
- совместим
- обновлен
- устарев
---
# Compatibility Skill

## Apply when
Existing callers, persisted formats, configuration, CLI/API behavior, or mixed-version upgrade paths can be affected.

## Mandatory rules
- Identify the compatibility surface before editing: callers, stored data, config, protocol, CLI flags, or generated artifacts.
- Preserve existing behavior by default; breaking changes require explicit authorization and a migration/deprecation path.
- Keep readers tolerant before writers emit a new format when rolling/mixed-version operation matters.
- Do not silently reinterpret old data or defaults.

## Decision rules
- Prefer additive fields/options and staged deprecation over in-place semantic changes.
- Version persisted formats/protocols when ambiguity would otherwise be permanent.
- A migration is part of the feature if existing installations cannot adopt the change safely without it.

## Failure modes
Renaming/removing public fields with no transition, new required config with no default/migration, writers that old readers cannot tolerate, and tests that cover only fresh installs.

## Quality gates
- Existing behavior has regression coverage.
- Upgrade from a representative previous state is exercised for material compatibility changes.
- Any intentionally unsupported downgrade/break is explicit rather than implied.
