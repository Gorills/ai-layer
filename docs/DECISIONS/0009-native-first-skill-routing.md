# ADR 0009 — Host-native skill relevance, AI Layer authoritative content

**Status:** Accepted  
**Version:** 0.10.3

## Context

The pre-0.10.3 Skill Layer contained an active AI Layer relevance planner. `memory_context` classified skills as `required`, `recommended` and `on_demand`, eagerly injected required/recommended skill cores into the context budget, and propagated that plan into worker/bootstrap/dashboard behavior.

Current official platform contracts for Cursor, OpenAI Codex and Google Antigravity all provide native Agent Skills discovery and host-side relevance selection. Codex and Antigravity explicitly document metadata-first progressive disclosure; Cursor documents automatic discovery, host relevance decisions and progressive/on-demand resources. Running an AI Layer classifier in front of those mechanisms duplicates responsibility and consumes context before the host has selected a domain skill.

## Decision

For Cursor, Codex and Antigravity:

- **The host owns skill relevance selection.**
- **AI Layer owns canonical skill content, validation, versioning, installation/update, selective retrieval, native descriptor synchronization and observability.**
- `memory_context` never automatically injects domain skill bodies.
- AI Layer publishes thin native Agent Skills descriptors containing only routing metadata plus instructions to retrieve the smallest useful authoritative section through `skill_get`.
- Full skill retrieval remains explicit through `skill_get(section="full")`; exact `##` sections are preferred.
- Global Cursor and Codex descriptors share the standard `~/.agents/skills` catalog. Antigravity uses its documented `~/.gemini/config/skills` global path. Project descriptors use `.agents/skills` when repository writes are allowed.
- For `external`/`strict-private` projects, project-specific descriptors are namespaced and published to user-level catalogs. Their host-visible description includes the exact registered project scope so native routing does not treat the descriptor as globally relevant.
- New/updated skills fail the description quality gate before installation. Pre-existing legacy skills with invalid routing descriptions are retained in the canonical store but blocked from native publication so one bad legacy skill cannot brick the whole upgrade.
- Legacy `ProjectSkill` rows and `SkillPlanCreated` events remain readable historical data only. They do not participate in new runtime decisions.
- `skill_search` is an explicit/manual diagnostic lookup only; it is not a runtime router.

## Removed responsibility

AI Layer no longer owns:

- required/recommended/on-demand classification;
- relevance scoring for supported native-skill hosts;
- automatic required/recommended core injection;
- planner-derived worker routing state;
- planner-derived dashboard state;
- new planner/autoload telemetry.

## Rules boundary

Always-loaded rules/bootstrap retain only control-plane invariants that must be known before domain work: orchestrator role, sequential Task discipline, project identity/recovery, privacy/provenance and the minimal native-skill retrieval contract. Domain expertise remains in skills.

## Consequences

Positive:

- no competing host + AI Layer relevance routers;
- zero automatic domain-skill body cost in `memory_context`;
- one canonical skill source across hosts;
- selective authoritative retrieval remains observable and testable;
- zero-footprint modes remain compatible with project-specific expertise.

Tradeoffs:

- host activation itself is not observable by AI Layer; only configured catalogs and subsequent `skill_get` calls are observable;
- exact host prompt/schema assembly and billing remain `HOST_HIDDEN`;
- a legacy custom skill with an invalid description is not auto-discoverable until its metadata is repaired.

## Official platform contracts used

- Cursor Agent Skills: https://cursor.com/docs/skills
- Cursor Rules: https://cursor.com/docs/rules
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- OpenAI Codex AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Google Antigravity Skills: https://antigravity.google/docs/skills
- Google Antigravity Rules: https://antigravity.google/docs/ide/rules
- Google Antigravity Plugins: https://www.antigravity.google/docs/plugins
