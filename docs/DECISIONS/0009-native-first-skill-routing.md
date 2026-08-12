# ADR 0009 — Host-native skill relevance, AI Layer authoritative content

**Status:** Accepted, amended 2026-08-12  
**Introduced:** 0.10.3  
**Activation amendment:** 0.12.x

## Context

The pre-0.10.3 Skill Layer contained an active AI Layer relevance planner. `memory_context` classified skills as `required`, `recommended` and `on_demand`, eagerly injected required/recommended skill cores into the context budget, and propagated that plan into worker/bootstrap/dashboard behavior.

Current supported platform contracts for Cursor, OpenAI Codex and Google Antigravity provide native Agent Skills discovery and host-side relevance selection. Running an AI Layer classifier in front of those mechanisms duplicates responsibility and consumes context before the host has selected a domain skill.

The first native-first implementation correctly removed the duplicate relevance router, but published thin pointer-style `SKILL.md` files. After host activation, a weak model still had to choose an exact section and call `skill_get` before it received the professional guidance. A second hard `core <= 2400 characters` path could also cut the selected guidance mid-section. That saved context at the wrong boundary: after relevance had already been established.

## Decision

For Cursor, Codex and Antigravity:

- **The host owns skill relevance selection.**
- **AI Layer owns canonical skill content, validation, versioning, installation/update, native publication, selective retrieval and observability.**
- `memory_context` never automatically injects domain skill bodies.
- AI Layer publishes a host-compatible native `SKILL.md` for each enabled skill containing compact routing frontmatter (`name`, `description`) followed by the **complete authoritative canonical skill body**.
- Once the host activates a skill, the model receives the complete professional guidance. AI Layer does not require a second content-routing decision merely to obtain the skill that was already selected.
- `skill_get` remains available for explicit/manual retrieval, exact-section rereads, the mandatory `ai-layer-workflow` startup core, package metadata/assets, diagnostics and API/dashboard use. It is not the normal gateway from native activation to domain competence.
- `skill_get(section="core")` returns complete configured entry sections. Character budgets are soft compatibility hints only; AI Layer must never truncate a semantic section in the middle.
- Global Cursor and Codex native skills share the standard `~/.agents/skills` catalog. Antigravity uses its documented `~/.gemini/config/skills` global path. Project skills use `.agents/skills` when repository writes are allowed.
- For `external`/`strict-private` projects, project-specific skills are namespaced and published to user-level catalogs. Their host-visible description includes the exact registered project scope so native routing does not treat the skill as globally relevant.
- New/updated skills fail the description quality gate before installation. Pre-existing legacy skills with invalid routing descriptions are retained in the canonical store but blocked from native publication so one bad legacy skill cannot brick the whole upgrade.
- Legacy `ProjectSkill` rows and `SkillPlanCreated` events remain readable historical data only. They do not participate in new runtime decisions.
- `skill_search` is an explicit/manual diagnostic lookup only; it is not a runtime router.

## Removed responsibility

AI Layer does not own:

- required/recommended/on-demand classification;
- relevance scoring for supported native-skill hosts;
- automatic required/recommended core injection;
- planner-derived worker routing state;
- planner-derived dashboard state;
- new planner/autoload telemetry;
- a second mandatory section-selection step after native activation.

## Rules boundary

Always-loaded rules/bootstrap retain only control-plane invariants that must be known before domain work: orchestrator role, Task/Epic navigation discipline, project identity/recovery, privacy/provenance and the native-skill activation contract. Domain expertise remains in skills.

The special `ai-layer-workflow` skill is still explicitly loaded as `core` after `memory_context` because it is mandatory control-plane procedure rather than optional domain relevance. Its core is semantic and complete, not character-clipped.

## Context-economy boundary

Context economy is achieved by **not loading irrelevant skills**, not by degrading the skill already selected as relevant.

Before activation the host can use compact skill metadata for discovery. After activation the selected skill is allowed to spend the context needed to make a weak model competent in that domain. `skill_get(section=...)` can still reduce repeated or manual retrieval when only one exact topic is needed.

## Consequences

Positive:

- no competing host + AI Layer relevance routers;
- zero automatic domain-skill body cost in `memory_context`;
- weak models receive complete professional guidance after native activation;
- no semantic section can be silently cut at an arbitrary character boundary;
- one canonical skill source across hosts;
- exact-section retrieval remains available and observable;
- zero-footprint modes remain compatible with project-specific expertise.

Tradeoffs:

- one activated skill now costs approximately the size of that skill instead of a pointer stub; this is intentional because relevance has already been established;
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
