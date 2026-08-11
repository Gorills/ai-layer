# Local AI Development Layer 0.11.0 — Verified Project Knowledge Architecture Report

## Executive Summary

The v0.11.0 iteration changes the responsibility of AI Layer Memory rather than making the previous semantic source index more sophisticated.

The previous design copied eligible current repository files into `Knowledge`, chunked them, embedded them, and returned semantically similar source excerpts through `memory_context`. That duplicated a capability already provided by native coding hosts and created a freshness/context problem: the agent could receive up to 4,000 characters of copied current source and still had to inspect the repository because the repository remained authoritative.

The implemented ownership model is now:

```text
HOST NATIVE TOOLS       current source discovery/read/search
AI LAYER SCANNER        deterministic repository evidence + freshness
PROJECT KNOWLEDGE       durable, reviewed semantic understanding
TASK ENGINE             review-gated knowledge publication
DECISION/HISTORY        durable engineering rationale and prior work
```

`ai-layer scan` is retained, but it no longer claims to understand the project or build a second code-search index. It records deterministic file evidence, hashes, manifests/import signals, test/config/runtime candidates and freshness inputs. Semantic knowledge is model-authored only during explicit managed work, must cite scanned repository evidence, and is not authoritative until an independent reviewer actually retrieves the DRAFT cards and passes the review.

`memory_context` is now a compact task project brief. It returns relevant VERIFIED Project Knowledge, relevant task/decision history, source pointers, stale warnings and bounded scanner evidence. It returns **zero raw current-source memory characters**. The agent then uses Cursor/Codex/Antigravity native tools to inspect the current implementation.

No Epic capability was implemented. Existing repository `epic/*` files are ordinary legacy evidence only.

## Problem Found in 0.10.3

The old source-memory path was technically functional, but its product boundary was weak:

```text
repository
  -> scanner
  -> source chunks
  -> embeddings
  -> pgvector Knowledge(kind=file/...)
  -> memory_context semantic hits
  -> coding agent
  -> native source search/read anyway
```

This had four practical problems:

1. **Duplicated current-source retrieval.** Native coding hosts already own current file discovery and reading.
2. **Freshness ambiguity.** A copied chunk can become stale while the repository changes.
3. **Context waste.** The prior `memory_context` had a 4,000-character memory budget that could be consumed by raw source excerpts.
4. **Wrong abstraction.** File chunks answer “what text resembles my prompt?”, not the more valuable cross-chat questions: “what is this subsystem?”, “why is it structured this way?”, “what was previously decided?”, “what must not be broken?”, and “where should I inspect the current implementation?”.

The example discussed during this iteration illustrated the problem: a food-search task received large Docker/documentation diagnostics, unrelated route inventories and raw test code, while only one hit was directly useful. The new acceptance test encodes the opposite contract.

## Architecture Decision

### Core principle

> Host knows current code. AI Layer knows the project.

### Responsibility split

```text
REPOSITORY
    |
    v
Deterministic Evidence Scan
    |
    +---------------------> freshness / fingerprints
    |
    v
Explicit Knowledge Onboarding Task
    |
    v
Mapper (IMPLEMENT)
    |
    +--> evidence-backed DRAFT cards
    |
    v
Fresh independent Reviewer (REVIEW)
    |
    +--> knowledge_list(DRAFT, source_task_id)
    |        |
    |        +--> durable KnowledgeReviewInspected event
    |
    +--> findings -> FIX -> fresh REVIEW
    |
    v
VERIFIED Project Knowledge
    |
    +--> task-aware retrieval
    +--> source pointers
    +--> stale invalidation
    |
    v
memory_context(task)
    |
    v
Compact Task Project Brief
    |
    v
Weak/cheap coding agent
    |
    v
Host-native current-source inspection
```

The accepted design is recorded in `docs/DECISIONS/0010-verified-project-knowledge.md`.

## Scanner Role After Redesign

The scanner remains important, but its contract is narrower and more reliable.

It owns objective evidence such as:

- file identity and repository-relative paths;
- content hashes and scanner schema;
- language/import/purpose/risk signals;
- manifests and dependency evidence;
- configuration/migration/test/documentation evidence;
- candidate entrypoints and framework signals;
- change detection and evidence freshness.

It does **not** publish semantic Project Knowledge by itself. Scanner-derived compatibility fields are explicitly labelled evidence/candidates rather than reviewed architecture truth.

### Removed source-index behavior

New scans no longer:

- chunk current source for semantic memory;
- embed current-source chunks;
- create `Knowledge(kind="file")` rows;
- create scanner-authored `architecture` or `project-intelligence` semantic rows for task retrieval;
- return current source excerpts from `memory_context`.

Scanner schema is now **v4**.

## Project Knowledge Contract

Project Knowledge reuses the existing `Knowledge` persistence table under the distinct kind:

```text
project-knowledge
```

No new Alembic revision was required.

A card is structured around a stable knowledge key and contains:

- category;
- title;
- bounded summary;
- claims;
- constraints/invariants;
- explicit unknowns;
- repository evidence paths;
- evidence fingerprints;
- source Task identity;
- lifecycle/provenance metadata.

Supported categories include overview, subsystem, runtime, data, integration, deployment, testing, invariant and fragile-area.

Every card must cite at least one safe repository-relative path present in the latest deterministic scan. Absolute paths and parent traversal are rejected. The card stores the supporting file content hash and scanner schema so later source changes can invalidate only affected knowledge.

### Lifecycle

```text
DRAFT
  -> VERIFIED       successful independent review
  -> SUPERSEDED     task cancelled or replaced

VERIFIED
  -> STALE          supporting evidence changed/disappeared
  -> SUPERSEDED     newer verified card replaces same key
```

A DRAFT is never returned as authoritative task memory.

A project reports an initial knowledge baseline as ready only when it has a VERIFIED `overview` card. A single verified subsystem card is deliberately insufficient.

## Model-authored, Review-gated Knowledge

The scanner is not allowed to promote semantic conclusions automatically.

A knowledge-authoring operation is allowed only when:

- a managed Task is active;
- its workflow is review-gated (not `micro` or `analysis_only`);
- the active stage is delegated IMPLEMENT or FIX;
- the caller presents the exact delegated `worker_id`.

The worker can write **DRAFT only** through `knowledge_draft_upsert`.

### Technical reviewer inspection gate

The design does not rely only on telling a reviewer “please review the memory”.

When a task contains Project Knowledge drafts, `REVIEW -> pass` is rejected with `PROJECT_KNOWLEDGE_REVIEW_REQUIRED` until the active REVIEW stage has retrieved that task’s DRAFT cards through the Project Knowledge read path. That read records a durable `KnowledgeReviewInspected` event bound to the active review stage.

After FIX, a new REVIEW must inspect the updated drafts again; a prior reviewer inspection does not authorize a later publication.

A clean passing review publishes the task’s DRAFT cards as VERIFIED. Cancellation supersedes unpublished drafts.

This proves that the review path was exercised. It does **not** claim to prove that an LLM reasoned correctly; evidence-backed claims and independent model review remain the quality mechanism.

## Initial Legacy Onboarding

Onboarding is intentionally explicit and relatively expensive. `scan` never launches an LLM automatically.

Recommended flow:

```text
1. ai-layer scan
2. explicit managed STANDARD task
   complexity=high
   uncertainty=high
   cost_policy=quality
3. IMPLEMENT worker = Project Mapper
4. Mapper reads scanner evidence + current source with host-native tools
5. Mapper writes evidence-backed DRAFT cards
6. fresh REVIEW worker verifies cards against current source
7. findings -> existing FIX -> fresh REVIEW loop
8. passing review publishes VERIFIED baseline
```

For a large/critical legacy system, later independent audit tasks can use different strong/fast models to challenge coverage or particular subsystems. They should not be chained as sequential summary rewriters, because that encourages correlated assumptions and weakens provenance.

The architecture therefore supports the intended human workflow without hard-coding Composer, Grok, Gemini or any other provider/model identity.

## `memory_context` After Redesign

The memory response is now conceptually a **Task Project Brief**, not a dump of internal scanner state.

Relevant fields are:

- `knowledge_state`;
- `task_brief.verified_knowledge`;
- `task_brief.stale_knowledge`;
- `task_brief.relevant_history`;
- `task_brief.relevant_decisions`;
- `task_brief.source_pointers`;
- `scanner_evidence` (small, explicitly unreviewed navigation evidence);
- compact freshness.

A representative food-search acceptance case requires that the response return:

- the Food Search subsystem card;
- implementation/test source pointers;
- existing known behavior;
- relevant prior Task history;
- relevant decisions if any;
- freshness contract.

It must not return:

- giant Docker internals;
- all mobile routes;
- broad unrelated documentation inventory;
- raw source excerpts/chunks.

This contract is covered by `test_food_search_memory_context_is_a_compact_project_brief_not_diagnostic_dump`.

### Compatibility envelope

For compatibility, the current MCP `memory_context` response still carries policy, response contract, Task runtime and tool guidance. These are explicitly separate responsibilities even though they share one transport response today.

This iteration deliberately did not redesign the whole orchestration/bootstrap API. Further separation is a context-economy opportunity, not a reason to conflate those fields with Project Knowledge.

## `memory_search` Semantics

`memory_search` now searches only review-gated Project Knowledge.

It is no longer a semantic current-source search tool.

Current implementation details must be retrieved with native host source tools. `decision_search` remains the dedicated path for durable architectural/engineering rationale. Task/WorkSession history is kept distinct from Project Knowledge and may be summarized into the task brief when relevant.

This is an intentional semantic narrowing of the existing API: callers that treated `memory_search` as a code-search replacement must now use native source search/read.

## Work History and Decisions

The redesign deliberately avoids treating old Markdown files as the only source of history.

AI Layer already owns durable workflow state, so relevant completed Task history can be exposed directly as structured information: goal, outcome, affected work and completion evidence where available.

Decisions remain a separate first-class concept because they answer a different question:

- Project Knowledge: **how is this project/subsystem understood?**
- Task History: **what work happened before?**
- Decision History: **why was a consequential choice made?**

Repository ADRs and old project documentation can be evidence during onboarding, but are not silently upgraded into authoritative AI Layer knowledge without review.

## Epic Boundary

No Epic subsystem was added or inferred from existing repository files.

Current project paths such as `epic/archive/...` are treated as ordinary legacy project documentation/evidence. A future AI Layer Epic capability must have its own lifecycle, persistence and orchestration contract rather than inheriting semantics from old repository artifacts.

## Freshness and Incremental Maintenance

Project Knowledge cards store fingerprints for supporting evidence.

When `scan` observes a material change to a cited source path, only cards supported by changed/disappeared evidence move from VERIFIED to STALE. Unrelated source changes do not invalidate unrelated cards.

This enables an economical long-lived workflow:

```text
initial expensive onboarding
        |
        v
verified baseline
        |
        +-- completed Tasks add history
        +-- Decisions add rationale
        +-- source changes invalidate affected cards
        +-- explicit later Task refreshes stale/weak areas
```

The design explicitly avoids calling a strong model after every commit.

## Upgrade Strategy

No database migration or destructive reset is performed.

On first scanner-schema-v4 refresh of a pre-v0.11 project:

- old scanner semantic `Knowledge` rows of kind `file`, `architecture` and `project-intelligence` are removed lazily;
- deterministic `ProjectFile` evidence is refreshed;
- curated `project-knowledge` rows are preserved;
- Decisions, Tasks and WorkSessions are preserved;
- vector drift re-embeds only semantic durable knowledge that still needs vectors (curated Project Knowledge and Decisions), not the whole source tree.

The migration head remains `0012_architecture_hardening`.

## Observability

New durable knowledge events:

- `KnowledgeDraftUpdated`;
- `KnowledgeReviewInspected`;
- `KnowledgePublished`.

Context reporting can identify:

- reviewed knowledge returned;
- stale knowledge returned;
- raw-source-memory regression;
- Project Knowledge baseline state;
- observed knowledge tool calls.

The report still distinguishes AI Layer-observed/configured facts from hidden host behavior. It does not claim that a model cognitively used a returned card, nor does it claim exact provider token billing.

## Context Economy

### Before (0.10.3)

The `memory_context` source-memory budget was:

```text
MEMORY_CONTEXT_MEMORY_CHAR_BUDGET = 4000
```

Those characters could be current-source scanner chunks, as seen in the real example supplied for this redesign.

### After (0.11.0)

```text
context_budget.raw_source_memory_chars = 0
```

The same 4,000-character internal budget constant now bounds curated Project Knowledge card material, not copied current-source excerpts.

Therefore the automatic current-source memory cost changed from **up to 4,000 chars (~1,000 very rough token-equivalents at 4 chars/token)** to **0 chars**. This is an approximate context comparison only, not provider billing.

The MCP catalog grew from 35 to 37 tools because the redesign adds only:

- `knowledge_list`;
- `knowledge_draft_upsert`.

No classifier/router/graph service was added.

## Implementation Footprint

Relative to the supplied 0.10.3 source tree before adding this report/evidence artifact:

- 8 files added;
- 1 old wheel removed;
- 42 files modified.

Important new modules:

- `src/ai_layer/memory/knowledge_contract.py`;
- `src/ai_layer/memory/knowledge_store.py`;
- `src/ai_layer/memory/history.py`;
- `src/ai_layer/application/knowledge.py`;
- `src/ai_layer/mcp/tools/knowledge.py`;
- `tests/test_project_knowledge.py`;
- `docs/DECISIONS/0010-verified-project-knowledge.md`.

## Test Report

Only commands actually executed are represented as PASS.

### Project Knowledge / scanner targeted regression

Executed with a **test-only local SQLAlchemy Vector type stub** because this container lacks the `pgvector` Python package:

```text
PYTHONPATH="/tmp/ai-layer-test-stubs:src" python -m pytest -q \
  tests/test_project_knowledge.py \
  tests/test_tool_guidance.py \
  tests/test_scanner.py \
  tests/test_incremental_memory.py \
  tests/test_project_intelligence.py
```

Result: **46 passed**.

This covers, among other things:

- no raw-source Knowledge creation on scan;
- scanner cleanup of legacy semantic rows;
- evidence-path safety;
- DRAFT/VERIFIED/STALE lifecycle;
- reviewed overview baseline requirement;
- changed supporting source invalidation;
- technical review-inspection publication gate;
- compact food-search task brief;
- no giant Docker/route/source dump.

### Broad dependency-light/stubbed regression

A broad 26-module regression set was executed with the same test-only Vector type stub after the final code changes in that phase.

Result: **300 passed**.

This included Project Knowledge, scanner, tasks/adaptive workflow, freshness/sync, sessions/config/policy/registry/privacy, native skills, integrations, architecture/observability/orchestrator behavior, runtime upgrade/release reproducibility and installation-contract coverage.

### Full test tree with test-only Vector stub

Executed:

```text
PYTHONPATH="/tmp/ai-layer-test-stubs:src" \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -o addopts='' -q tests
```

Result: **387 passed, 17 failed, 7 skipped**.

All 17 failures are environment collection/runtime failures caused by the missing `mcp` SDK (`ModuleNotFoundError: No module named 'mcp'`) in MCP/API/dashboard-dependent tests. The seven PostgreSQL-marked tests are skipped because this environment has no real PostgreSQL/pgvector service.

Therefore this command is **NOT a full-suite PASS**.

### Context trace subset

Executed excluding the two tests that require the missing MCP SDK:

```text
PYTHONPATH="/tmp/ai-layer-test-stubs:src" python -m pytest -o addopts='' -q \
  tests/test_context_trace.py \
  -k 'not mcp_execution_boundary_records_successful_tool_delivery and not mcp_boundary_resolves_bound_project_for_telemetry'
```

Result: **4 passed, 2 deselected**.

### Architecture gate

```text
python scripts/architecture_gate.py
```

Result: **PASS**. No import or capability cycles; hard function-size limit satisfied.

### Governance gate

The Task transition publication gate is governance-sensitive. After adding ADR 0010, tests and human-visible rationale, the local governance baseline was re-acknowledged through the repository’s canonical baseline process, then:

```text
python scripts/governance_gate.py
```

Result: **PASS** for the local tamper-evident baseline.

This is not production trust; the release manifest still requires protected-branch review/signing policy.

### Migration gate

```text
python scripts/migration_gate.py
```

Result: **PASS**. Head remains `0012_architecture_hardening`; no new migration was introduced.

### Native skill gate

```text
python scripts/skill_gate.py
```

Result: **PASS**: 42 built-in skills, no active AI Layer relevance router, no automatic domain-skill injection.

### Release/deterministic wheel gate

```text
python scripts/release_gate.py --check-deterministic-wheel
```

Result: **PASS** for the 0.11.0 release metadata/wheel reproducibility checks in this environment.

### Canonical quality gate diagnostic

Executed:

```text
python scripts/quality_gate.py --deterministic-wheel --continue-on-failure
```

Result: **NOT PASS**.

Environment blockers:

- formatting: `ruff` missing;
- lint: `ruff` missing;
- typing: `mypy` missing;
- canonical test collection: real `pgvector` Python dependency missing.

Architecture, migration, skill, governance and packaging/release sub-gates passed in that diagnostic run.

The canonical quality gate must be rerun on the supported release environment before production promotion.

## Environment Limitations

Current container:

- Python: **3.13.5**;
- official release runtime: **CPython 3.12.x Linux x86_64**;
- no real PostgreSQL/pgvector service;
- no `mcp` SDK;
- no `ruff`;
- no `mypy`.

The local Vector stub was used only to exercise ORM-independent/unit behavior. It is not included in the project or release archive and is not PostgreSQL/pgvector integration evidence.

## Remaining Risks

### P0

None identified in the implemented source architecture.

### P1 — release/promotion evidence

1. Run canonical quality gate on supported CPython 3.12 with exact release dependencies (`ruff`, `mypy`, `pgvector`).
2. Run PostgreSQL/pgvector migration and semantic retrieval integration tests against a real service.
3. Run MCP black-box tests with the actual MCP SDK/host integration.
4. Preserve protected-branch/external review requirements for the governance-sensitive Task transition change.

### P2 — product effectiveness

1. The redesign makes Project Knowledge structurally safer/useful, but it has not yet proven that weak models complete real tasks more cheaply or accurately.
2. Knowledge completeness is not automatically knowable. A VERIFIED overview proves reviewed baseline existence, not exhaustive subsystem coverage.
3. The compatibility `memory_context` envelope still carries policy/Task/tool-guidance fields; future context-economy work may separate these transport surfaces.
4. Multi-model onboarding quality must be evaluated with real projects; adding more models must remain an explicit cost/coverage decision rather than automatic consensus theater.

### P3 — compatibility cleanup

Scanner-derived `Project.architecture_summary` / project-intelligence compatibility fields remain available but are labelled unreviewed evidence. They can be deprecated later if no external consumer needs them.

## Independent Post-implementation Audit

1. **Who now discovers current code?**  
   Cursor/Codex/Antigravity native source tools. AI Layer does not default to a second current-source retrieval path.

2. **Does an active semantic raw-source index remain?**  
   No for new scanner/runtime behavior. Scanner schema v4 lazily removes legacy `file`/`architecture`/`project-intelligence` semantic rows.

3. **Who authors semantic project knowledge?**  
   A delegated Mapper/Fixer model during explicit review-gated managed work.

4. **Can scanner inference become authoritative automatically?**  
   No. Scanner evidence is explicitly unreviewed navigation evidence.

5. **How does knowledge become VERIFIED?**  
   DRAFT -> active independent reviewer retrieves that task’s drafts -> review passes -> Task Engine publishes VERIFIED cards.

6. **What makes knowledge stale?**  
   A change/disappearance of supporting deterministic repository evidence fingerprints.

7. **What happens when no verified baseline exists?**  
   `memory_context` still returns bounded scanner evidence/history/decisions as available and recommends explicit onboarding; it does not automatically spend strong-model tokens or invent knowledge.

8. **Can the agent still inspect implementation details?**  
   Yes, and it is expected to do so with native host tools using Project Knowledge source pointers as navigation hints.

9. **Were Epics implemented?**  
   No. Existing `epic/*` files are legacy evidence only.

10. **How will usefulness be proven?**  
    With black-box A/B tasks: same weak model and project, native tools alone vs native tools + reviewed Project Knowledge. Measure exploratory tool calls/files/tokens, wrong architecture assumptions, review findings, fix rounds and accepted-result quality.

## Product Acceptance Recommendation

The next validation should not be another large architecture expansion. Use a real medium/large legacy repository to:

1. build one reviewed Project Knowledge baseline with a strong Mapper + independent Reviewer;
2. run a fixed set of representative weak-model tasks with/without Project Knowledge;
3. inspect context telemetry and Task outcomes;
4. retain/expand the feature only if it measurably reduces repeated exploration or review failures without lowering final quality.

That experiment is the actual proof that this Memory Layer deserves to remain part of AI Layer.

## v0.11.3 Context Compiler hardening

`memory_context` now treats explicit continuation as a distinct presentation problem. Generic continuation wording is not a semantic memory query. The response provides compact recent-work metadata and Task navigation, then points the agent to `session_restore(latest)`; current source remains authoritative. Previous task internals/reviewer reasoning are not copied into continuation context.

Scanner evidence is fail-quiet when its snapshot is not current: stale/refreshing/missing scanner facts and scanner-derived project profile are withheld. This prevents an older snapshot (for example, Markdown-only project metadata) from contradicting newer Task history that already created Python/package/test files. No persistence or Project Knowledge lifecycle change is involved.


## v0.11.4 Policy/Bootstrap context economy

The remaining constant context overhead was audited after Skill, raw-source-memory and continuation reductions. The audit confirmed that AI Layer itself duplicated static workflow/policy across host-native global instructions, project-level rule files, MCP server instructions and every `memory_context` response.

Static delivery now has one owner: the global native bootstrap. Standard projects retain only sparse host MCP bindings carrying the exact canonical project root. The bundled default policy remains stored/manageable locally but is no longer retransmitted by `memory_context`; only user-customized global policy, project-specific rules and strict-private constraints are dynamic. `task_next` remains the authoritative procedural owner after bootstrap.

The useful weak-model quality floor was not discarded: evidence-first edits, smallest coherent change, real verification, avoidance of speculative dependencies, high-impact caution and irreversible-action authorization are distilled into the global bootstrap. Project-level text bridges are removed only when AI Layer-owned; user-authored AGENTS/CLAUDE/legacy-rule content is preserved.

Measured reference surfaces from v0.11.3 to v0.11.4:

- global AI Layer bootstrap: 6209 -> ~1.9k characters;
- project AI Layer text bridge: 1704 -> 0 installed characters (187-character compatibility renderer remains internal only);
- MCP server instructions: 6525 -> ~0.3k characters;
- bundled default+runtime policy returned by ordinary `memory_context`: 4974 -> 0 characters when the user/project has no custom policy;
- response contract representation: 564 -> 126 characters.

This is a context-delivery ownership change, not a relaxation of Task, privacy, provenance, review or verification invariants.
