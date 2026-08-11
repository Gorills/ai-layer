# Local AI Development Layer

Version 0.11.4 pre-Epics native-first/context-economy candidate.

Local AI Development Layer is a single-machine control plane for durable AI-assisted engineering. It provides project identity/context, expert skills, sequential durable Tasks, worker provenance, executable verification, observability, dashboard projections, host integrations and immutable release/update infrastructure.

**Epics are intentionally not implemented in this version.** The repository contains only an empty architectural extension boundary for the next capability.

## Runtime model

- Development source lives only in this repository.
- Installed runtime/state lives at machine scope.
- Target repositories never receive AI Layer source code. Standard mode may receive sparse generated/reversible workspace MCP bindings; `external` keeps AI Layer state entirely machine-side; `strict-private` adds provenance/privacy enforcement to external attachment.

## Supported release runtime

The release manifest targets Linux x86_64 with CPython 3.12.x and pinned release dependencies. Development may happen elsewhere, but promotion evidence must come from the supported runtime.

## Basic lifecycle

```bash
./install.sh
ai-layer init /path/to/project
ai-layer scan /path/to/project
ai-layer service status
ai-layer dashboard
```

The daemon owns the always-on control plane/dashboard. `ai-layer dashboard` checks service availability and opens the browser rather than starting an independent dashboard backend.

For a zero-repository-footprint privacy mode on an existing Git repository:

```bash
ai-layer init /path/to/project --external
ai-layer init /path/to/project --private
```

## Verified Project Knowledge

AI Layer does **not** compete with Cursor/Codex/Antigravity for current-code discovery. `ai-layer scan` now collects deterministic repository evidence and freshness data; host-native tools remain authoritative for reading/searching current source. Durable AI Layer memory stores what is expensive to reconstruct across chats/models: reviewed project overview/subsystem knowledge, invariants, source pointers, decisions and completed-work history.

Project Knowledge is model-authored only during an explicit review-gated managed Task. The mapper can write evidence-backed `DRAFT` cards; an independent REVIEW must retrieve and verify those drafts before the Task Engine publishes them as `VERIFIED`. Supporting source changes mark only affected cards `STALE`. `memory_context` compiles a small presentation for the request: semantic reviewed knowledge for ordinary tasks, inventory-first context for Project Knowledge audits, and session-first context for explicit continuation. Stale scanner/profile facts are withheld, and raw current-source chunks are never copied into the brief.

After the deterministic scan, inspect readiness with:

```bash
ai-layer memory status --path /path/to/project
ai-layer memory knowledge --path /path/to/project --status VERIFIED
```

A project without a reviewed overview reports onboarding as recommended; AI Layer does not automatically spend model tokens or silently manufacture a baseline. See `docs/PROJECT_KNOWLEDGE_ARCHITECTURE_REPORT.md` and ADR `docs/DECISIONS/0010-verified-project-knowledge.md`.

## Native-first skills

Cursor, Codex and Antigravity own skill relevance through their native Agent Skills mechanisms. AI Layer keeps one authoritative skill store, validates routing descriptions, synchronizes thin native descriptors and serves targeted instructions through `skill_get`. `memory_context` never preloads domain skill bodies. Global Cursor/Codex descriptors share `~/.agents/skills`; Antigravity uses `~/.gemini/config/skills`; standard project skills use `.agents/skills`. External/strict-private project skills remain repository-zero-footprint through namespaced user-level descriptors.

See `docs/NATIVE_SKILL_ARCHITECTURE_REPORT.md` and ADR `docs/DECISIONS/0009-native-first-skill-routing.md`.

## Context and skill economy monitoring

AI Layer automatically records what **AI Layer itself** observes/configures: host rule/bootstrap files, MCP server instructions and tool-contract catalog, `memory_context` payload/components, native skill descriptor catalogs, explicit `skill_get` fetches, Task navigation results and other MCP result sizes. Host-native skill selection is marked `HOST_HIDDEN`; AI Layer does not claim to know the host's complete prompt or exact billing tokens. Diagnostic state is secret-redacted and stored outside the target repository.

The current portable report is generated automatically at context/skill/stage boundaries and can be refreshed/exported at any time:

```bash
ai-layer context-report --path /path/to/project --output /tmp/ai-layer-context-report.json
```

Internal location: `~/.ai-layer/projects/<project_id>/diagnostics/context-monitor/context-report-latest.json`. The report intentionally distinguishes configured/observed AI Layer context from host-hidden Cursor system prompts, full chat context, exact model tokenizer/cache behavior and whether the model actually used a delivered skill. Token counts are approximate (`UTF-8 bytes / 4`) and are for relative economy analysis, not billing reconciliation. See `docs/CONTEXT_MONITORING.md`.

## Static policy/bootstrap ownership

AI Layer static workflow/engineering guidance is installed once through each host's native global instruction surface. Standard projects do **not** receive duplicate AI Layer text in `AGENTS.md`, `CLAUDE.md`, `.cursor/rules` or `.agents/rules`; exact project identity is carried by sparse workspace MCP bindings instead. `memory_context` returns only dynamic policy that differs by user/project/privacy state. The bundled default policy remains locally managed but is not retransmitted on every context request. Runtime stage procedure is owned by `task_next`, not repeated in static rules. See ADR `docs/DECISIONS/0013-single-owner-static-bootstrap.md`.

## Updates

The client command is:

```bash
ai-layer update
```

It consumes a signed publisher manifest, verifies its detached signature and artifact SHA-256, safely extracts the immutable release, runs release preflight and delegates migration/atomic switch/service restart/health/project reconciliation to the installer. A real publisher manifest URL and public trust key must be provisioned by the release channel; this source archive does not invent one.

## Quality

Canonical local/CI/release gate:

```bash
python scripts/quality_gate.py --deterministic-wheel
```

See `QUALITY_GATES.md`. Missing Ruff/mypy or an unsupported dependency environment causes a failure.

## Architecture and state

Read in this order:

1. `PROJECT_CHARTER.md`
2. `ARCHITECTURE.md`
3. `QUALITY_GATES.md`
4. `CURRENT_STATE.md`
5. `ROADMAP.md`
6. relevant `docs/DECISIONS/*.md`

Source code, executable tests and migrations override prose when they disagree.
