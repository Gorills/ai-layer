# Independent Skill Architecture & Context Economy Redesign — Final Report

**Project:** Local AI Development Layer  
**Implemented version:** 0.10.3  
**Audit input:** the supplied 0.10.2 source archive only  
**Decision:** native-first Skill architecture implemented

## Executive Summary

The supplied source contained a genuine duplicate relevance layer. AI Layer had its own runtime planner that classified skills as `required`, `recommended` and `on_demand`, eagerly inserted required/recommended skill cores into `memory_context`, propagated the plan to workers/bootstrap, recomputed it for dashboard state, and emitted planner/autoload telemetry.

That responsibility overlaps the documented native Agent Skills behavior of Cursor, OpenAI Codex and Google Antigravity. All three discover native skills and let the host agent decide relevance. Codex and Antigravity explicitly document metadata-first progressive disclosure; Cursor documents automatic discovery/relevance selection and on-demand progressive resources.

0.10.3 removes the active AI Layer relevance router instead of replacing it with another classifier. The resulting ownership model is:

```text
HOST OWNS RELEVANCE DECISION
AI LAYER OWNS AUTHORITATIVE SKILL CONTENT
```

Runtime flow:

```text
USER TASK
   |
   v
Cursor / Codex / Antigravity
   |
   v
native Agent Skills discovery + host relevance decision
   |
   v
thin native SKILL.md descriptor
   |
   v
MCP skill_get(slug, exact section)
   |
   v
AI Layer canonical Skill Store
```

`memory_context` no longer inserts domain skill bodies. Full skill retrieval remains available, but targeted section retrieval is the intended default.

## Official Platform Findings

Only official product documentation was used for the platform contract.

### Capability matrix

| Capability | Cursor | Codex | Antigravity |
|---|---|---|---|
| native skill discovery | CONFIRMED | CONFIRMED | CONFIRMED |
| automatic selection | CONFIRMED | CONFIRMED | CONFIRMED |
| metadata-first loading | PARTIAL | CONFIRMED | CONFIRMED |
| progressive disclosure | CONFIRMED | CONFIRMED | CONFIRMED |
| project skills | CONFIRMED | CONFIRMED | CONFIRMED |
| global skills | CONFIRMED | CONFIRMED | CONFIRMED |
| MCP available from skill | PARTIAL | CONFIRMED | PARTIAL |
| Agent Skills standard compatibility | CONFIRMED | CONFIRMED | CONFIRMED |
| full SKILL lazy loading | PARTIAL | CONFIRMED | CONFIRMED |

`PARTIAL` means the official docs support the architectural direction but do not document the exact stronger claim needed to call that row fully confirmed.

### Cursor

Official sources:

- https://cursor.com/docs/skills
- https://cursor.com/docs/rules

Confirmed contract:

- Agent Skills are an open standard.
- Cursor automatically discovers skills and presents available skills to Agent; Agent decides when they are relevant.
- Manual `/` invocation is supported.
- Project locations include `.agents/skills/` and `.cursor/skills/`; global locations include `~/.agents/skills/` and `~/.cursor/skills/`.
- `name` and `description` are required; `description` is explicitly used to determine relevance.
- `paths`, `disable-model-invocation` and arbitrary `metadata` are supported optional fields.
- Skill resources/references are loaded progressively/on demand.
- Rules are prompt-level guidance; when applied, rule content is included at the start of model context. Always-Apply rules are therefore the wrong place for ordinary domain expertise when a dynamic skill can carry it.

Conservative boundary:

Cursor docs do not make the same exact statement as Codex/Antigravity that *only* `name` + `description` are the pre-activation skill payload and then the entire `SKILL.md` is lazy-read. The redesign therefore does not claim visibility into Cursor's hidden prompt assembly. It relies only on the documented discovery/relevance/progressive contract.

### OpenAI Codex

Official sources:

- https://developers.openai.com/codex/skills
- https://learn.chatgpt.com/docs/agent-configuration/agents-md

Confirmed contract:

- Skills build on the open Agent Skills standard.
- Codex starts with each skill's `name` and `description`; Codex additionally includes the skill file path.
- The initial skill list has an explicit context budget: at most 2% of the model context window, or 8,000 characters when the context size is unknown. Descriptions can be shortened and skills can be omitted if the list is too large.
- After Codex selects a skill it reads the full `SKILL.md`.
- Implicit activation depends on `description`; explicit invocation is also supported.
- Repository skills use `.agents/skills`; user skills use `$HOME/.agents/skills`; admin/system scopes also exist.
- Plugin metadata can explicitly declare MCP tool dependencies.
- `AGENTS.md` is read before work and merged into the prompt chain up to the configured project-doc budget, so it is an always/persistent instruction surface rather than a substitute for dynamic domain skills.

### Google Antigravity

Official sources:

- https://antigravity.google/docs/skills
- https://antigravity.google/docs/ide/rules
- https://www.antigravity.google/docs/plugins

Confirmed contract:

- Agent Skills are an open standard.
- At conversation start the agent sees skill names/descriptions; if a skill is relevant it reads the full instructions.
- The documentation explicitly defines progressive disclosure as Discovery (`name` + `description`) -> Activation (read full `SKILL.md`) -> Execution.
- The agent decides automatically from context; users can mention a skill explicitly.
- Workspace skills use `.agents/skills`; global skills use `~/.gemini/config/skills`.
- `description` is the routing surface and should contain concrete recognition keywords.
- Rules can be Manual, Always On, Model Decision or Glob; global rules live in `~/.gemini/GEMINI.md`.
- Plugins can package skills, rules and MCP server definitions together, confirming coexistence of these extension surfaces. The standalone common `SKILL.md` frontmatter does not document a universal MCP dependency field, so the cross-host descriptor does not invent one.

## Confirmed / Rejected Assumptions

| Assumption | Status | Evidence | Impact |
|---|---|---|---|
| Cursor/Codex/Antigravity already own native skill relevance selection | CONFIRMED | official Skills docs | remove AI Layer runtime relevance planner |
| all three can consume a common project `.agents/skills/<skill>/SKILL.md` artifact | CONFIRMED | official Skills locations | one common renderer for project skills |
| all three use the same global path | REJECTED | Antigravity uses `~/.gemini/config/skills`; Cursor/Codex support `~/.agents/skills` | path adapters only, not three renderers |
| every host officially guarantees exactly `name` + `description` and nothing else before activation | PARTIAL | explicit for Codex/Antigravity; not equally explicit for Cursor | report host prompt details as hidden; do not overclaim |
| a universal SKILL.md MCP dependency field exists across all three | REJECTED | Codex has optional OpenAI metadata; Antigravity plugin can bundle MCP; Cursor common Skill docs do not define a universal field | descriptors simply instruct use of the already-configured AI Layer MCP tool |
| weak-model reliability requires an AI Layer classifier before native skills | REJECTED for these hosts | official host relevance mechanisms + description routing surface | improve descriptions/gates instead of adding another router |
| three independent host-specific skill implementations are required | REJECTED | shared Agent Skills format/project path | common descriptor renderer + install-path adapters |
| database reset/migration is required to remove the planner | REJECTED | planner state is runtime/read-side; historical rows/events can remain inert | no destructive migration |

## Old Architecture — factual source path

The supplied archive implemented this active path:

```text
user task
  -> memory_context
  -> AI Layer planner / relevance scoring
  -> required / recommended / on_demand
  -> eager required+recommended core loading (6000-char budget)
  -> returned skill_plan + skills
  -> bootstrap/worker instructions require following AI Layer plan
  -> optional skill_get for deeper sections
```

Observed implementation responsibilities included:

- `src/ai_layer/skills/planner.py`: handcrafted runtime scoring/classification;
- `src/ai_layer/skills/service.py`: routing APIs and project selection;
- `src/ai_layer/memory/service.py`: planner call + automatic skill-core budgeting/injection;
- scanner `ProjectSkill` selection;
- worker delegation contracts containing planner tiers;
- dashboard recomputation of `required/recommended/on_demand`;
- `SkillPlanCreated` / `SkillLoaded(mode=autoload_core)` and planner-specific findings;
- project bridge content instructing the host to follow the AI Layer plan.

This was not just management/validation. It was a second relevance router in front of host-native routing.

## New Architecture — implemented source path

```text
host native catalog
  -> host relevance decision
  -> thin native descriptor
  -> explicit skill_get
      -> exact section (default preference)
      -> full only when explicitly necessary
  -> canonical AI Layer Skill Store
```

Implementation seams:

- `src/ai_layer/skills/native_descriptor.py` — common descriptor rendering and description/catalog quality validation;
- `src/ai_layer/skills/native_files.py` — native target ownership, locations, cleanup and catalog inspection;
- `src/ai_layer/skills/native_sync.py` — global/project publication and upgrade-safe blocked-legacy handling;
- `src/ai_layer/skills/native.py` — thin compatibility facade;
- `src/ai_layer/skills/service.py` — canonical loading and selective section/full retrieval, no relevance selection;
- `src/ai_layer/memory/service.py` — project/history context only; domain skill injection explicitly zero;
- integrations — native descriptors synchronized automatically on install/project/skill changes;
- observability — configured catalog + observed `skill_get` telemetry, with host activation marked hidden.

## Native Descriptor Strategy

Canonical global skills remain in the AI Layer Skill Store. AI Layer materializes thin host-compatible `SKILL.md` files instead of copying full domain content into each host directory.

Global paths:

```text
Cursor + Codex  -> ~/.agents/skills/<slug>/SKILL.md
Antigravity     -> ~/.gemini/config/skills/<slug>/SKILL.md
```

Standard project-specific skills:

```text
<repo>/.agents/skills/<slug>/SKILL.md
```

`external` / `strict-private` project-specific skills:

```text
user-level host catalog / ai-layer-<project-hash>-<slug>/SKILL.md
```

The external descriptor's host-visible `description` includes the exact registered project scope. This prevents a project-only skill, which must live in a global filesystem location for zero footprint, from presenting itself as globally relevant.

## Description Quality Gate

New/updated skills are rejected before installation when the routing description is missing, too short/long, generic, merely repeats the name, or lacks concrete routing terms. All 42 bundled skills pass the gate.

The gate also reports cheap lexical Jaccard overlap warnings. This is validation only: it does not score or route runtime work and therefore does not recreate the removed planner.

Upgrade behavior is deliberately tolerant for existing data: a pre-existing legacy custom skill with an invalid description remains in the canonical store and remains explicitly retrievable, but its native descriptor is blocked until metadata is fixed. Other valid descriptors still synchronize.

## Removed Components / Runtime Responsibilities

Removed or deactivated:

- active `skills/planner.py`;
- active domain `SkillPlan` contract;
- `skill_plan_for_query`, `select_skills_for_project` and runtime tier selection;
- automatic required/recommended skill-core injection in `memory_context`;
- planner-driven scanner project skill selection;
- planner tiers from worker delegation contract;
- dashboard `Router plan` / required/recommended/on-demand recomputation;
- new planner/autoload telemetry such as `RECOMMENDED_SKILLS_AUTOLOADED` and `UNPLANNED_SKILL_FETCH`;
- old project AI Layer skill bridge artifacts and their runtime role;
- obsolete routing metadata from all 42 bundled skill manifests.

Historical DB/event records are retained readable but inert. `SkillPlanCreated` remains in the event schema only for historical decoding.

## Preserved Components

Preserved because they solve responsibilities not owned by the hosts:

- canonical Skill Store;
- skill import/install/update/remove lifecycle;
- version/trust/package assets;
- `skill_get` and exact section retrieval;
- full retrieval on explicit request;
- description/native descriptor validation;
- global/project native synchronization;
- strict-private/zero-footprint behavior;
- memory, Tasks, orchestration, verification and dashboard capabilities;
- context monitoring and durable historical telemetry.

`skill_search` remains an explicit/manual local metadata search for cases where a human/agent has a concrete expertise gap but does not know the slug. It is not called by `memory_context` and is not a default relevance path.

## Rules vs Skills Audit

Always-loaded bootstrap/rules were reduced to control-plane invariants:

- top-level orchestrator role;
- sequential Task/stage discipline;
- canonical project identity/recovery;
- mutation/read-only/provenance boundaries;
- privacy/zero-footprint behavior;
- one minimal statement that host-native skills own relevance and `skill_get` retrieves authoritative sections.

Django, Docker, CSS, database migrations, security patterns and other domain bodies are not placed in the always-loaded bridge.

## Context Economy

Measurements compare the supplied pre-redesign source with 0.10.3. Approximate tokens are `ceil(UTF-8 bytes / 4)` and are not billing/tokenizer claims.

### Automatic domain skill bodies in `memory_context`

Representative old planner runs:

| Task | Old automatic skill chars | Old approx tokens | New automatic domain skill bytes/tokens |
|---|---:|---:|---:|
| Django migration + tests | 6000 | ~1500 | 0 / 0 |
| Docker production deployment/volumes | 4353 | ~1089 | 0 / 0 |
| React/CSS accessibility/design | 6000 | ~1500 | 0 / 0 |

Two representative tasks hit the old hard 6000-character skill budget before the host had made a native relevance decision.

### Configured always/persistent AI Layer surfaces

These are measured separately because AI Layer cannot know how a host combines/caches them into an actual prompt.

| Surface | Before bytes / approx tokens | After bytes / approx tokens |
|---|---:|---:|
| critical orchestrator contract | 1302 / ~326 | 1302 / ~326 |
| global bootstrap | 5382 / ~1346 | 5540 / ~1385 |
| project always-on bridge | 10062 / ~2516 | 1549 / ~388 |
| MCP instructions | 5745 / ~1437 | 5815 / ~1454 |

The large win is removal of domain autoload plus the project bridge reduction. Small increases in global/MCP guidance state the new ownership/retrieval invariant explicitly.

### Native catalog

For the 42 bundled skills:

- catalog validation: 42 skills, 0 issues, 0 lexical-overlap warnings;
- canonical `name` + `description` values: **4409 bytes (~1103 tokens)** before host-added paths/serialization;
- serialized YAML frontmatter bodies (`name` + `description` lines): **5375 bytes (~1344 tokens)**;
- aggregate thin descriptor files on disk: **47109 bytes**; this is **not** claimed as prompt cost because the host progressively loads skills;
- descriptor sizes: 1054–1300 bytes, average 1121.6 bytes.

Codex explicitly budgets its initial skill list. Cursor/Antigravity exact host prompt assembly remains `HOST_HIDDEN`.

### MCP tool catalog

The public AI Layer MCP tool count did not change: **36 -> 36**.

Static source proxy (function signatures + tool docstrings, not host-serialized schema):

- before: 13,054 bytes;
- after: 13,358 bytes;
- delta: +304 bytes.

The increase is the explicit native-skill retrieval guidance in skill tool descriptions. Exact host MCP schema prompt overhead is not observable here and is not claimed.

## Context Monitoring After Redesign

Monitoring distinguishes:

- `AI_LAYER_OBSERVED` — `memory_context`, explicit `skill_get` calls/results, section/full choice, bytes and approximate tokens, repeated fetches;
- `AI_LAYER_CONFIGURED` — native descriptor catalog, rule/bootstrap files, MCP instructions/tool catalog;
- `HOST_HIDDEN` — whether/why the host selected a skill, host system prompt, full chat assembly, cache/compaction and exact billing tokens.

Obsolete new-runtime findings for recommended autoload/unplanned planner fetches are removed. Legacy trace fields remain readable as historical evidence.

## Migration / Backward Compatibility

- No DB schema migration was required.
- No destructive reset is performed.
- Existing historical planner telemetry remains readable.
- Existing AI-owned project skill bridge files are removed on integration sync/upgrade.
- Native descriptors are synchronized as part of global/project integration and skill lifecycle operations.
- One bad pre-existing custom description no longer prevents the valid catalog from upgrading; that specific skill is reported blocked from native publication.
- Task Engine, memory persistence, MCP transport, dashboard, privacy modes, project registration and worker lifecycle were not redesigned.

## Test Report — only commands actually executed

Successful in this container:

```text
PYTHONPATH=src python -m pytest -q tests/test_native_skills.py tests/test_skills.py tests/test_integrations.py
41 passed

PYTHONPATH=src python -m pytest -q tests/test_architecture_gate.py tests/test_native_skills.py tests/test_skills.py tests/test_integrations.py
52 passed

PYTHONPATH=src python -m pytest -q tests/test_context_trace.py -k 'not mcp_execution_boundary and not mcp_boundary_resolves and not context_report_cli' tests/test_project_intelligence.py tests/test_config.py tests/test_policy.py tests/test_registry.py tests/test_privacy.py
35 passed

python scripts/skill_gate.py
PASS: 42 bundled skills, native catalog valid, no automatic domain injection

python -m compileall -q src alembic scripts tests
PASS
```

The architecture gate was also executed independently after module separation and returned `ok: true`, with no new native-skill maintainability warning.

Environment-limited checks:

```text
PYTHONPATH=src python -m pytest -q
NOT PASS / collection stopped: 17 ModuleNotFoundError errors for pgvector

python scripts/quality_gate.py --deterministic-wheel
NOT PASS / stopped immediately: required tool missing: ruff
```

The container is CPython 3.13.5 while the release manifest supports CPython 3.12.x, and the pinned runtime stack/MCP SDK/PostgreSQL/Ruff/mypy are not available here. These checks are therefore not relabeled PASS.

Final release verification:

```text
python scripts/release_gate.py --check-deterministic-wheel
PASS: architecture, governance, migrations, native skill gate and deterministic wheel
wheel SHA-256: b9be3e0e868eb6255c7e41c4d787e1665f3938b08dfeaf1830dcbcf278fa064a
```

Machine-readable measurements are included at `docs/evidence/0.10.3-native-skill-context-economy.json`.

## Independent Re-audit

1. **Who determines skill relevance now?** Cursor/Codex/Antigravity native Agent Skills mechanisms.
2. **Is there a second routing path?** No active one. Manual `skill_search` is explicit diagnostics, not automatic routing; historical planner records are inert.
3. **What data does the agent constantly receive?** Host/rule/bootstrap/tool surfaces configured by the integration plus the host's native skill metadata behavior. AI Layer does not claim the host's exact merged prompt.
4. **Which domain instructions are constantly loaded by AI Layer?** None through `memory_context`; automatic domain-skill body bytes are zero.
5. **How is a full skill obtained?** Explicit `skill_get(slug=..., section="full")`.
6. **Can only one section be obtained?** Yes, with an exact `##` section name in `skill_get`.
7. **What happens if no skill is needed?** No domain skill body is fetched by AI Layer; no automatic skill content cost is paid by `memory_context`.
8. **How much did automatic overhead fall?** Representative old domain autoload 4353–6000 chars (~1089–1500 tokens) -> 0; project bridge 10062 -> 1549 bytes.
9. **Are there host-specific hacks?** Only documented filesystem-location adapters and the zero-footprint namespacing strategy. There is no host-specific classifier.
10. **Can another native-skill platform be added without rewriting the Skill Store?** Yes. A standard-compatible platform needs a publication/location adapter; canonical parsing/retrieval/validation remains unchanged.

## Remaining Risks

### P0

None identified in the redesigned Skill Layer during this audit.

### P1

**Supported-runtime promotion evidence is incomplete in this container.** Full pytest/quality gate cannot run because the environment lacks the pinned 3.12 runtime dependencies (`pgvector`, MCP SDK, Ruff/mypy, PostgreSQL service). The source/release gate evidence here must not substitute for a clean supported-runtime CI/install run.

### P2

- Actual black-box activation behavior in installed Cursor/Codex/Antigravity was not executable from this audit container. Official contracts are confirmed, but exact host prompt delivery remains hidden by design.
- A pre-existing legacy custom skill with a poor description is deliberately blocked from native discovery until repaired; it remains in the canonical store and does not block the rest of the upgrade.
- Cursor does not document its pre-activation payload with the same exactness as Codex/Antigravity, so the report intentionally marks metadata-first/full-SKILL lazy details as PARTIAL rather than guessing.

### P3

The static MCP tool-description proxy grew by 304 bytes to make selective retrieval semantics explicit. The public tool count remains unchanged at 36, and no MCP API redesign was introduced.

## Final Architecture Acceptance

The implemented architecture satisfies the target responsibility split:

```text
                    USER REQUEST
                         |
                         v
        Cursor / Codex / Antigravity
                         |
                 native skill routing
                         |
                         v
                 thin native SKILL
                         |
                         v
                  MCP skill_get
                         |
                         v
             AI Layer Skill Store

memory_context ---X---> automatic domain skill injection
```

No replacement classifier, embedding router, regex mega-router, LLM router, microservice, message broker or Epic subsystem was added.
