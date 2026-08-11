# Current State — v0.11.4 context-economy candidate

## Implemented source state

The pre-Epics foundation now has two explicit native-first boundaries:

- **Skills:** Cursor/Codex/Antigravity own skill relevance; AI Layer owns canonical skill content, validation, native descriptor sync and targeted `skill_get` retrieval.
- **Current source:** host-native code search/read owns current implementation discovery; AI Layer no longer builds a parallel semantic source index.
- **Scanner:** `ai-layer scan` owns deterministic repository evidence, hashes/file identity, bounded project signals and freshness/invalidation. Scanner inference is labelled evidence, not reviewed semantic truth.
- **Project Knowledge:** model-authored evidence-backed cards capture durable overview/subsystem knowledge, invariants, constraints, explicit unknowns and source pointers.
- **Knowledge publication:** Mapper/Fixer can write only DRAFT cards in review-gated Tasks. A passing reviewer must first retrieve the task's DRAFT cards; successful review publishes VERIFIED cards. A reviewed overview is required for baseline readiness.
- **Freshness:** supporting-file fingerprint changes move only affected VERIFIED cards to STALE. Cancelled-task drafts become SUPERSEDED.
- **History:** durable completed Tasks, Decisions and WorkSessions remain separate first-class history sources. Repository `epic/*` files remain legacy evidence; AI Layer Epics are still intentionally unimplemented.
- **Context:** ordinary coding tasks get a compact semantic Project Knowledge brief; explicit Project Knowledge audits get a complete compact inventory-first view with prior reviewer reasoning excluded; explicit continuation prompts get a session-first compact continuation brief. Stale scanner/profile facts are withheld. Automatic raw-source memory and automatic domain skill bodies are both zero.
- **Policy/bootstrap:** static AI Layer rules have one owner in each host’s global native instruction surface. Standard projects use sparse workspace MCP bindings for exact root identity; bundled default policy/static workflow manuals are not repeated through `memory_context`. Only customized global policy, project-specific rules and strict-private constraints are dynamic.

## Upgrade behavior

No Alembic migration is required. Scanner schema is v4. The first freshness refresh of an older project lazily removes obsolete scanner semantic rows (`file`, `architecture`, `project-intelligence`) and reparses deterministic evidence; curated Project Knowledge, Decisions and history are preserved. No destructive database reset is performed.

## Validation status in this build environment

Successful checks are recorded in `docs/PROJECT_KNOWLEDGE_ARCHITECTURE_REPORT.md`. Architecture and migration/skill static gates can run here. Unit tests that need ORM Vector columns are exercised with a test-only local `pgvector` SQLAlchemy type stub; this is **not** real PostgreSQL/pgvector integration evidence.

The container does not provide the supported CPython 3.12 runtime stack, real PostgreSQL/pgvector service, MCP SDK, Ruff or mypy. Therefore canonical quality, PostgreSQL/MCP black-box and supported-runtime promotion checks must not be represented as PASS unless separately executed on the supported release host.
