# Audit remediation plan — AI Layer 0.14.0

> **Status:** rewritten execution plan. Original independent audit remains
> evidence, not a literal implementation program.  
> **Release decision:** do not promote 0.14.0.  
> **Audited / current HEAD:** `b552da646b15bfd504984a89b8ae577e1c909a45`  
> **How to run:** one Task at a time, STANDARD host-native loop
> IMPLEMENT (coder) → independent REVIEW → FIX → REVIEW. Do not start the next
> Task until the current one is terminal.

This file is the sequential work list for closing the 0.14.0 audit. Source,
migrations and tests remain code truth. Do not mark a finding closed by editing
this file. Close it with a code change plus regression evidence.

## Verdict

The original audit’s findings are real at this revision. Its four-step
remediation program is not. Isolation, agent-visible truth, skill packaging,
Dashboard product UI and four-host black-box acceptance are different kinds of
work. Execute Programs A then B in order. Program C starts only after T9.
Promotion black-box is not a coding Task.

This checkout is the AI Layer **source** repository. It is not an AI Layer
target. Do not call installed AI Layer project/MCP tools against it. Do not use
ambient `~/.ai-layer`, a machine Dashboard, or a global `ai-layer` binary as
product evidence. Use this worktree, its `.venv`, tests, migrations and gates.

## Original evidence (preserved)

Confirmed at the audited revision:

- Version, wheel SHA-256, Alembic `0001_initial` → `0017_work_spine` and
  preflight were internally consistent.
- External / strict-private targets stay zero-footprint.
- Green gates did not exercise the P1 scenarios below.
- Repository `AGENTS.md` is not shipped into target projects.

Release-blocking observations (IDs kept):

| ID | Observation | Original recipe to reject |
| --- | --- | --- |
| P1-1 | `command_receipts` unique on global `command_id`; request hash omits project; MCP `_scoped()` stamps the requested root onto a replayed foreign Work | none — fix as specified in T1 |
| P1-2 | Shipped `ai-layer-workflow` omits Work lifecycle, continues only via Task/Epic, forbids translating search queries | do not duplicate the always-on bootstrap |
| P1-3 | `project_status` policy is first 12k chars; custom global text is composed first, so project/privacy rules can be cut | do not add paginated full-policy retrieval |
| P1-4 | Native sync writes `SKILL.md` only; package store may hold `scripts/` / `references/` / `assets/` | do not blindly copy executables into host skill dirs |
| P1-5 | Native skill roots are not symlink-checked; sync can write through a symlink | none — fix as specified in T2 |
| P1-6 | One stale v1/v2 descriptor yields `native_catalog.ready=true`; Claude can look ready from bootstrap alone | do not fail a whole upgrade because optional Claude CLI MCP is missing |
| P1-7 | After 300s heartbeat, active Work stays durable but drops out of focus, attention and Dashboard `idle/healthy` | do not set `live=true` for stale runs |
| P1-8 | Activity Task/Epic filters read `RuntimeEventContext`, while Task/Epic producers call `append_event` without it; Epic types missing from milestone allowlist | do not rewrite historical RuntimeEvent rows |
| P1-9 | Verification runner persists argv and up to 16k raw stdout/stderr; Dashboard renders them | do not copy the RuntimeEvent allowlist onto 16k of stdout |
| P1-10 | Overview GET / freshness mkdir `.ai-layer/` on standard targets | do not treat this as completing Phase 3 machine-owned state |
| P1-11 | Work list/detail API exists; browser has no Work route/UI; portfolio lacks Now / Needs attention / Recently completed | this is Phase 1 product work, not an isolation hotfix |

## Orchestrator contract (every Task)

1. Read this file’s **current Task only**, then `AGENTS.md`, `QUALITY_GATES.md`
   and the ADRs named in that Task. Inspect current source and `git status`.
   Dirty `README.md` is unrelated; do not include it.
2. Reproduce the defect on current source before editing.
3. Run STANDARD stages in this chat (or the host orchestrator):
   - **IMPLEMENT (coder):** smallest coherent change, tests, no extra Tasks.
   - **REVIEW (reviewer):** read-only, defect-first, independent of the coder.
   - **FIX (fixer):** only accepted review findings, then REVIEW again.
4. Verification: focused pytest for the changed behavior; `make fast-gate`
   before any commit. If the Task touches migrations/constraints, also
   `make postgres-gate`. `make preflight` before push/PR, not as a substitute
   for the Task’s regression test.
5. SQLite may characterize logic. It does not prove PostgreSQL uniqueness,
   advisory locks or upgrade safety.
6. Stop when the Task is terminal. Hand off the next Task’s prompt from this
   file. Do not start the following Task in the same change.
7. Do not commit unless the human asks. Do not amend this plan’s historical
   evidence section.

Suggested `task_create` shape if the host orchestrator needs it: `workflow` /
`risk` / `complexity` / `uncertainty` / `cost_policy` = `auto` unless a Task
says otherwise. Force STANDARD review; do not downgrade to MICRO.

---

## Program A — isolation and privacy

### T1 — Project-scoped Work idempotency

- **Closes:** P1-1
- **Owns:** `application/commands.py`, `application/work.py`, `db/models.py`,
  Alembic, `mcp/tools/work.py` / `mcp/runtime.py` `_scoped()`, tests
- **ADR:** `DECISIONS/0020-durable-work-spine-and-truthful-observability.md`

**Goal:** The same idempotency key and payload in project B must not replay
project A’s Work. Lookup, uniqueness, request hash and PostgreSQL advisory lock
must include project identity. A replayed result must not be decorated with the
caller’s `project_root` when the receipt belongs to another project.

**Acceptance criteria:**

- Same `command_id` + same payload in two projects executes two handlers and
  returns two Work identities.
- Same `command_id` + same payload retry **inside one project** still returns
  the original result without a second mutation.
- Same `command_id` + different payload still raises key-reuse.
- MCP `work_begin` / checkpoint / terminal replay cannot present a foreign Work
  as belonging to the requested root.
- Alembic head is a new linear revision after `0017_work_spine`. Existing
  receipts remain valid. PostgreSQL unique constraint matches the lookup key.

**Constraints:**

- Do not invent a second idempotency mechanism. Extend `execute_idempotent` /
  `CommandReceipt`.
- Include `project_id` in the advisory-lock key if uniqueness becomes
  `(project_id, command_id)`.
- `execute_idempotent` is also covered by `tests/test_architecture_hardening.py`;
  keep same-project retry behavior.
- No skill, Dashboard UI, policy, or native-sync changes.

**Verification:** regression tests for cross-project replay and MCP decoration;
`make fast-gate`; `make postgres-gate` for the new constraint/upgrade.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T1 only as STANDARD review-gated work: IMPLEMENT (coder) → independent read-only REVIEW → FIX if findings → REVIEW. Stop when T1 is terminal. Do not start T2.

Repo: /home/gorills/projects/ai-layer
HEAD at plan writing: b552da646b15bfd504984a89b8ae577e1c909a45 (0.14.0). Inspect current git status and source; do not trust this prompt as code truth.

This checkout is AI Layer source, not an AI Layer target. Do not call installed AI Layer project/MCP tools. Do not use ambient ~/.ai-layer, a machine Dashboard, or a global ai-layer binary as evidence. Use this worktree, its .venv, tests, migrations and gates.

Read AGENTS.md, QUALITY_GATES.md, DECISIONS/0020-durable-work-spine-and-truthful-observability.md, AUDIT.md section T1, then current:
- src/ai_layer/application/commands.py
- src/ai_layer/application/work.py
- src/ai_layer/db/models.py CommandReceipt
- src/ai_layer/mcp/runtime.py _scoped
- src/ai_layer/mcp/tools/work.py
- alembic/versions/0017_work_spine.py
- tests/test_architecture_hardening.py

Goal: Work idempotency is project-scoped. The same command_id+payload must not replay another project's Work. Request hash, uniqueness, lookup and PostgreSQL advisory lock must include project identity. MCP must not stamp the requested project_root onto a foreign replayed Work.

Acceptance:
- Two projects, same idempotency key and payload → two handler invocations, two Work identities.
- Retry inside one project → original result, no second mutation.
- Same key, different payload → key-reuse error.
- New linear Alembic revision after 0017_work_spine; existing receipts remain valid.
- MCP work_begin/checkpoint/terminal cannot present foreign Work as the requested root.

Constraints:
- Extend execute_idempotent/CommandReceipt; do not add a parallel idempotency store.
- Advisory lock key must match the uniqueness key.
- Leave README.md and any unrelated dirty files untouched. Do not implement T2–T9, Work UI, skill copy, or policy pagination.
- SQLite is not evidence for the unique constraint. Run focused tests, make fast-gate, and make postgres-gate.
- Commit only if the human asks.

Reproduce the cross-project replay on current source before editing.
```

### T2 — Symlink-safe native skill sync

- **Closes:** P1-5
- **Owns:** `skills/native_files.py` and callers
- **Depends on:** T1 terminal

**Goal:** Native skill synchronization must refuse symlink roots and parents
the same way other footprints already do. A `project/.claude/skills` (or
global native root) that is a symlink to an outside directory must not receive
writes, and the operation must fail closed.

**Acceptance criteria:**

- Symlinked native root or parent → no write outside the real intended tree,
  error surfaced, success not reported.
- Normal non-symlink sync still writes owned `SKILL.md` and removes owned
  stale descriptors.
- User-owned non-AI-Layer `SKILL.md` still conflicts rather than being
  overwritten.

**Constraints:**

- Reuse existing symlink checks; do not add a second path library.
- Do not copy `scripts/` / `references/` / `assets/` (that is Program C).
- No idempotency or Dashboard changes.

**Verification:** regression for symlink root/parent; `make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T2 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T2 is terminal. Do not start T3.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. This is AI Layer source, not an AI Layer target: no installed AI Layer project/MCP tools; no ambient ~/.ai-layer as evidence.

Read AGENTS.md, QUALITY_GATES.md, AUDIT.md section T2, then current src/ai_layer/skills/native_files.py and its callers/tests.

Goal: Native skill sync must fail closed when the native root or a parent is a symlink. It must not write through to an outside directory or report success.

Acceptance:
- Symlinked native root/parent → no outside write, error, not success.
- Normal non-symlink owned SKILL.md sync still works.
- Unowned SKILL.md still conflicts.

Constraints:
- Reuse existing symlink checks used by other footprints.
- Do not materialize package scripts/references/assets.
- Do not touch Work idempotency, verification redaction, Dashboard, or policy.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce the symlink write-through on current source before editing. Focused tests + make fast-gate.
```

### T3 — Verification evidence redaction

- **Closes:** P1-9
- **Owns:** `verification/runner.py`, Dashboard verification presenters/API
- **Depends on:** T2 terminal
- **ADR:** 0020 (Work evidence is safe metadata; raw command/output do not
  belong in human-facing Work evidence). Verification storage is a separate
  path and must still not leak secrets.

**Goal:** Persisted and Dashboard-rendered verification argv/stdout/stderr must
not expose secrets by default. Bound what is stored and shown. Keep enough
summary for a human to see that a check ran and whether it passed.

**Acceptance criteria:**

- Values equivalent to `--token=…`, `password=…` and similar secrets are
  redacted in persisted evidence and in default API/UI rendering.
- Default Dashboard/API does not dump raw 16k command output.
- A bounded non-secret summary (name/status/exit/short excerpt) remains.
- RuntimeEvent safe-payload allowlist is **not** copied onto verification
  stdout (that would hide legitimate check summaries).

**Constraints:**

- Reuse `redact_secrets` / existing redaction helpers where they fit.
- Do not make verification a sandbox. The runner stays trusted-local.
- No native-sync or Work-idempotency changes.

**Verification:** regression with secret-like argv/output; `make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T3 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T3 is terminal. Do not start T4.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools; no ambient runtime as evidence.

Read AGENTS.md, QUALITY_GATES.md, DECISIONS/0020-durable-work-spine-and-truthful-observability.md, AUDIT.md section T3, then current:
- src/ai_layer/verification/runner.py
- src/ai_layer/application/verification.py
- Dashboard API/presenters that render verification command/output
- src/ai_layer/observability/work_events.py SAFE_EVENT_* (do not copy this allowlist onto stdout)
- src/ai_layer/core/redaction.py

Goal: Verification argv and output must be secret-redacted in persist + default API/UI. Default view must not dump raw 16k stdout/stderr. Keep a bounded non-secret summary.

Acceptance:
- --token / password-like values redacted in stored evidence and default render.
- Default API/UI does not expose raw 16k output.
- Bounded summary remains (name/status/exit/short excerpt).
- Do not apply RuntimeEvent SAFE_EVENT allowlist to verification stdout.

Constraints:
- Reuse existing redact_secrets helpers.
- Do not turn the runner into a sandbox.
- Do not implement T4–T9 or Work UI.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce unredacted verification projection on current source before editing. Focused tests + make fast-gate.
```

---

## Program B — agent-visible truth

### T4 — Workflow skill matches runtime contract v2

- **Closes:** P1-2
- **Owns:** `src/ai_layer/builtin_skills/ai-layer-workflow.md` and skill/bootstrap
  contract tests
- **Depends on:** T3 terminal
- **ADR:** `DECISIONS/0019-live-agent-contract-and-semantic-governance.md`

**Goal:** The shipped workflow skill must not contradict `agent_runtime_contract()`
v2. Ordinary work uses WorkItem (`work_begin` + one terminal). Continuation
follows `project_status` work focus (Work, then Task, then Epic). Non-English
search uses one English code-centric primary query; original language is at
most one widening variant.

**Acceptance criteria:**

- Skill Decision rules / Workflow include the Work lifecycle and short-work
  budget.
- “Continue” is not Task/Epic-only.
- Search section matches contract v2 (English-first primary, identifiers
  verbatim, at most one original/mixed variant).
- Skill does not become a second copy of the always-on bootstrap.

**Constraints:**

- Edit skill prose and the tests that encode those semantics. Do not grow
  bootstrap merely to match the skill.
- No policy engine, native file, or Dashboard changes.

**Verification:** skill/bootstrap contract tests; `make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T4 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T4 is terminal. Do not start T5.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools.

Read AGENTS.md, QUALITY_GATES.md, DECISIONS/0019-live-agent-contract-and-semantic-governance.md, src/ai_layer/domain/agent_contract.py, AUDIT.md section T4, then current src/ai_layer/builtin_skills/ai-layer-workflow.md and the tests that assert skill/bootstrap semantics.

Goal: Shipped ai-layer-workflow must match runtime contract v2: WorkItem for ordinary work, continue via project_status focus (Work/Task/Epic), English-first code-centric search with at most one original-language variant.

Acceptance:
- Skill documents work_begin + one terminal; checkpoint only for milestones/blockers.
- Continue is not Task/Epic-only.
- Search matches agent_contract.py, not “send the raw Russian query and never translate”.
- Skill is not a duplicated bootstrap.

Constraints:
- Do not expand always-on bootstrap to paper over the skill.
- No policy/native-sync/Dashboard/idempotency work.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Focused contract tests + make fast-gate.
```

### T5 — Policy bound preserves project and privacy rules

- **Closes:** P1-3
- **Owns:** `policy/service.py`, `policy/project_policy.py`
- **Depends on:** T4 terminal
- **ADR:** 0020 (bounded `project_policy` is intentional)

**Goal:** Keep `PROJECT_POLICY_MAX_CHARS = 12000`. When truncation happens,
project rules and strict-private rules must remain in the agent-visible text.
`truncated=true` plus version/hash stay. No second paginated policy API.

**Acceptance criteria:**

- A long custom global prefix cannot drop project rules or strict-private
  rules from `project_policy.text`.
- Bound, `sha256` of full text, `chars`, and `truncated` remain correct.
- No new full-policy retrieval tool/endpoint.

**Constraints:**

- Prefer composition/truncation order (global may be shortened first).
- Do not raise the 12k limit to “fix” truncation.
- No skill or Dashboard UI changes.

**Verification:** tests with oversized global + project/privacy suffix;
`make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T5 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T5 is terminal. Do not start T6.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools.

Read AGENTS.md, QUALITY_GATES.md, DECISIONS/0020-durable-work-spine-and-truthful-observability.md, AUDIT.md section T5, then current src/ai_layer/policy/service.py and src/ai_layer/policy/project_policy.py.

Goal: Keep the 12k project_policy bound. Truncation must not drop project rules or strict-private rules. Do not add paginated/full policy retrieval.

Acceptance:
- Long custom global prefix cannot remove project/privacy text from project_status.project_policy.text.
- sha256 is of the full untruncated policy; truncated/chars remain truthful.
- No new policy pagination API.

Constraints:
- Do not raise PROJECT_POLICY_MAX_CHARS to hide the bug.
- No skill/Dashboard/Work changes.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce truncation dropping project rules before editing. Focused tests + make fast-gate.
```

### T6 — Stale Work stays in recovery and attention

- **Closes:** P1-7
- **Owns:** `application/work.py` `state()`, `application/project_intelligence.py`,
  `projections/dashboard_work_state.py`
- **Depends on:** T5 terminal
- **ADR:** 0020 — live requires a non-stale AgentRun. PRODUCT_GOAL — Needs
  attention includes stale / missing terminal.

**Goal:** Active Work whose AgentRun is stale (300s heartbeat) must not be
called live. It must appear in `work_attention`, continuation/recovery
guidance, and Dashboard Needs attention / project attention — not as
`idle/healthy` with “start new work”.

**Acceptance criteria:**

- `live=true` still requires a non-stale active AgentRun.
- Stale active Work is in attention/recovery payloads.
- `project_status` continuation does not tell the agent to start a new WorkItem
  while stale-active Work exists; it tells the agent to resume or terminate
  that WorkItem.
- Dashboard project_state is not `healthy` solely because the run went stale.
- Optional same-Task slice if cheap: `work_checkpoint` may set `linked_task_key`
  / `linked_epic_key` after begin. If that expands scope, omit it and leave it
  for Program C.

**Constraints:**

- Do not treat MCP bridges or open managed Tasks as live ordinary work.
- Do not build the Work list/detail UI (Program C).
- No schema change unless a new attention field is truly required; prefer
  existing work dicts.

**Verification:** stale-heartbeat fixture for status, project_status, overview
enrichment; `make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T6 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T6 is terminal. Do not start T7.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools.

Read AGENTS.md, QUALITY_GATES.md, PRODUCT_GOAL.md (Needs attention), DECISIONS/0020-durable-work-spine-and-truthful-observability.md, AUDIT.md section T6, then current:
- src/ai_layer/application/work.py state()
- src/ai_layer/work/service.py live/stale
- src/ai_layer/application/project_intelligence.py
- src/ai_layer/projections/dashboard_work_state.py

Goal: Stale active Work (300s heartbeat) must not be live, must appear in attention/recovery, and must not make Dashboard idle/healthy or tell agents to start new work.

Acceptance:
- live=true still requires non-stale AgentRun.
- Stale active Work is in work_attention and continuation.
- project_status does not instruct “start new work” while stale-active Work exists.
- Dashboard is not healthy solely because the run went stale.
- Do not build Work UI.

Constraints:
- Do not mark stale as live.
- MCP bridges / managed Tasks still do not prove live ordinary work.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce the stale-omission path before editing. Focused tests + make fast-gate.
```

### T7 — Task/Epic events are filterable

- **Closes:** P1-8
- **Owns:** Task/Epic `append_event` producers, `observability/work_events.py`,
  `projections/dashboard_activity.py` `MILESTONE_EVENT_TYPES`, Work detail
  timeline selection, `CURRENT_STATE.md` / `CHANGELOG.md` claims
- **Depends on:** T6 terminal

**Goal:** New Task/Epic lifecycle events must carry `RuntimeEventContext`
`task_id` / `epic_id` (and `work_id` when a Work is linked) so Activity v2
filters work. Add missing Epic types to the default milestone allowlist. Work
detail may include linked Task/Epic milestones without duplicating their
internal histories. Do not rewrite historical RuntimeEvent rows.

**Acceptance criteria:**

- A newly created Task appears in `activity_payload(task_id=...)`.
- A newly created/changed Epic milestone appears in default milestones and in
  `epic_id` filter.
- `CURRENT_STATE.md` / `CHANGELOG.md` no longer claim filters that old rows
  cannot satisfy; if historical events stay unfilterable, say so.
- No historical event rewrite.

**Constraints:**

- Prefer `append_contextual_event` at Task/Epic producers rather than a
  parallel journal.
- Backfill of old rows is out of this Task unless it is expand-only and tested.
- No Work UI screens.

**Verification:** producer + activity filter tests; `make fast-gate`. If a
migration is added, `make postgres-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T7 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T7 is terminal. Do not start T8.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools.

Read AGENTS.md, QUALITY_GATES.md, DECISIONS/0020-durable-work-spine-and-truthful-observability.md, CURRENT_STATE.md activity claims, AUDIT.md section T7, then current:
- src/ai_layer/observability/domain_events.py append_event
- src/ai_layer/observability/work_events.py append_contextual_event
- Task/Epic producers under src/ai_layer/tasks and src/ai_layer/application/epic_common.py
- src/ai_layer/projections/dashboard_activity.py MILESTONE_EVENT_TYPES and filters

Goal: New Task/Epic lifecycle events must populate RuntimeEventContext so Activity v2 task_id/epic_id filters return them. Include Epic types in the default milestone allowlist. Do not rewrite historical RuntimeEvent rows. Correct CURRENT_STATE/CHANGELOG if they overclaim.

Acceptance:
- New TaskCreated (and equivalent Epic milestones) are returned by activity_payload with that task_id/epic_id.
- Default milestones include Epic lifecycle types that product claims.
- Historical unfilterable rows are not silently rewritten; docs tell the truth.
- No Work UI.

Constraints:
- Prefer append_contextual_event at producers.
- Backfill only if expand-only and tested; otherwise leave old rows as-is and document it.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce empty task_id filter on a real TaskCreated before editing. Focused tests + make fast-gate; postgres-gate if you add a migration.
```

### T8 — Truthful per-host readiness

- **Closes:** P1-6
- **Owns:** `integrations/status.py` and Dashboard/status consumers
- **Depends on:** T7 terminal

**Goal:** `ready=true` must mean the expected owned descriptors and MCP/bootstrap
pieces for that host are present and current enough to be honest. One obsolete
v1/v2 file is not sufficient. Claude must not be green from bootstrap alone
when MCP/skills are missing. Optional Claude CLI failure must surface as
degraded/not-ready for that provider, not as a successful whole-product
upgrade hide.

**Acceptance criteria:**

- Native catalog readiness checks expected slugs/count/ownership, not
  `count > 0`.
- Claude `ready` is false when MCP or skills are absent (`mcp=None` /
  `skills=None` is not success).
- Upgrade/install still must not brick unrelated hosts because optional Claude
  CLI is missing; the Claude provider is degraded, others can be ready.
- Status payload distinguishes ready vs degraded vs not installed.

**Constraints:**

- Do not make Claude CLI a hard dependency of Cursor/Codex/Antigravity
  install success.
- No skill-resource copy (Program C).
- No Work UI.

**Verification:** fixtures with one stale descriptor, Claude bootstrap-only,
optional CLI missing; `make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T8 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T8 is terminal. Do not start T9.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools.

Read AGENTS.md, QUALITY_GATES.md, AUDIT.md section T8, then current src/ai_layer/integrations/status.py and its tests/Dashboard consumers.

Goal: Host readiness must be truthful. One stale native descriptor is not ready. Claude is not ready from bootstrap alone. Optional Claude CLI failure degrades Claude, it does not hide inside a green global upgrade.

Acceptance:
- native_catalog.ready requires expected owned descriptors, not count>0.
- Claude ready is false when mcp/skills are missing.
- Missing optional Claude CLI does not fail Cursor/Codex/Antigravity readiness; Claude is degraded.
- Payload distinguishes ready / degraded / not installed.

Constraints:
- Do not copy skill package resources.
- Do not add Work UI or install-transaction rewrite (Phase 3).
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce false-green catalog and Claude bootstrap-only paths before editing. Focused tests + make fast-gate.
```

### T9 — Read paths do not create project state

- **Closes:** P1-10
- **Owns:** `memory/freshness.py` `_memory_dir` / loaders,
  `observability/snapshot.py`, Dashboard GET overview
- **Depends on:** T8 terminal

**Goal:** Dashboard GET and other read projections must not create
`<project>/.ai-layer/` or `memory/` on a clean registered standard target.
Missing state is empty/absent, not mkdir. External/strict-private target
zero-footprint stays intact. Machine-owned memory dirs also must not be
created solely because a read ran.

**Acceptance criteria:**

- Overview GET against a clean registered standard project creates no new
  `.ai-layer/` or `.ai-layer/memory/` directories.
- Freshness/status still work when dirs already exist from real writes.
- External/strict-private targets remain without target-repo artifacts.
- `project_status` must not mkdir those paths either if it shares the loaders.

**Constraints:**

- This is not Phase 3 (do not move canonical state out of standard projects).
- Writes (scan, refresh job started by an explicit write path) may still
  create dirs. GET / snapshot / load metadata may not.
- Scheduling a background refresh from `project_status` is a separate smell;
  do not expand this Task into a refresh-runtime rewrite unless mkdir is
  caused by that path and can be stopped without dropping freshness reads.

**Verification:** clean-target GET/status test asserting no new dirs;
`make fast-gate`.

**Next-chat prompt:**

```text
Execute AUDIT.md Task T9 only as STANDARD review-gated work: IMPLEMENT → independent REVIEW → FIX → REVIEW. Stop when T9 is terminal. Do not start Program C.

Repo: /home/gorills/projects/ai-layer
Inspect current git status and source. AI Layer source, not a target: no installed AI Layer project/MCP tools.

Read AGENTS.md, QUALITY_GATES.md, AUDIT.md section T9, then current:
- src/ai_layer/memory/freshness.py
- src/ai_layer/observability/snapshot.py
- src/ai_layer/dashboard/api.py dashboard_overview
- src/ai_layer/application/project_intelligence.py freshness call

Goal: Read paths (Dashboard GET overview, load_scan_metadata, project_status freshness) must not mkdir .ai-layer or memory on a clean registered standard project.

Acceptance:
- Overview GET on a clean standard target creates no .ai-layer/ or .ai-layer/memory/.
- Reads still succeed with empty/absent metadata.
- Existing dirs from real writes keep working.
- External/strict-private target zero-footprint remains.

Constraints:
- Do not implement Phase 3 machine-owned-state migration.
- Do not build Work UI or copy skill resources.
- Leave unrelated dirty files untouched. Commit only if the human asks.

Reproduce GET mkdir on a clean registered target before editing. Focused tests + make fast-gate.
```

---

## Program C — after T9 only

These are real gaps. They are not part of the A→B sequence.

| ID | Outcome | Notes |
| --- | --- | --- |
| C1 | Dashboard Work list/detail UI plus portfolio Now / Needs attention / Recently completed | Closes P1-11. Backend `/api/v1/dashboard/work` already exists. Product slice, not a hotfix. |
| C2 | Skill packaged resources vs native `SKILL.md` | Closes P1-4. First decide: keep package-store resolution (current `skills/service.py` contract) and stop native skills from assuming relative `scripts/`, **or** materialize resources with the same ownership/symlink checks as T2. Do not copy blindly. Needs an explicit human/ADR choice if materialization is chosen. |
| C3 | `work_checkpoint` can set linked Task/Epic after begin | Only if omitted from T6. |
| C4 | Doc hygiene | Doctor must not point at missing `docs/BLACK-BOX_PROJECT_INTELLIGENCE_v0.7.0_RU.md`. Mark `NATIVE_SKILL_ARCHITECTURE_REPORT.md` and `EPICS_V1_SUPPORTED_HOST_ACCEPTANCE.md` superseded. Label MCP bridges as bridges, not “connected agents”. |
| C5 | OpenAPI/`contract_version` and MCP enum/length tightness | Schema hygiene, not isolation. |
| C6 | Transactional / restartable global install | ROADMAP Phase 3. Not this program. |
| C7 | Antigravity CLI `~/.gemini/antigravity-cli` | Unproven; not this program. |
| C8 | Move standard-mode mutable state out of the target repo | ROADMAP Phase 3. T9 is not this. |

Promotion reconsideration requires Programs A and B green, then
`release/release-manifest.json` black-box items on a supported host. That is a
release activity, not T1–T9.

## Confirmed strengths (do not regress)

- Version `0.14.0` agrees across source, package metadata, manifest and wheel.
- One linear Alembic chain ending at `0017_work_spine` (T1 adds the next).
- External / strict-private zero-footprint.
- Dashboard loopback, CSP, `no-store`, `nosniff`, HTML escaping.
- Activity pagination is bounded and cursor-stable.
- Work evidence allowlists on the WorkItem path (verification path is T3).
