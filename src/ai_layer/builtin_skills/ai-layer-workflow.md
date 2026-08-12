---
slug: ai-layer-workflow
description: AI Layer operating model for Project Intelligence, continuation, optional managed Tasks/Epics, review, recovery and durable project memory.
kind: core
keywords:
- ai layer
- project_status
- project_search
- knowledge_search
- task
- epic
- review
- recovery
entry_sections:
- Core contract
- Project intelligence
- Managed Tasks and Epics
---

# AI Layer Workflow

## Core contract

AI Layer is an engineering control plane, not a replacement agent runtime. The host (Cursor, Codex, Claude Code, Antigravity or another capable runtime) owns normal source reading, editing, shell commands, tests, code search, model choice and native subagents.

For registered-project work, call `project_status` first. Its purpose is to recover durable work state and Project Map freshness cheaply. After that, work natively unless an existing or explicitly selected managed Task/Epic requires its own lifecycle.

Current repository source is final code truth. Project Map, Project Knowledge, Decisions, Task state and Epic state are shortcuts to reduce repeated discovery and preserve continuity; they do not override current source.

## Project intelligence

Use each read channel for one job:

- `project_status`: **what is happening now?** Returns Git/worktree state, active Task, executing Epic, continuation focus and Project Map freshness without running workflow navigators or hashing the whole repository.
- `project_search`: **where should I look?** Searches a metadata-only Project Map containing paths, symbols, imports, compact purposes and related tests. It never returns stored source bodies. Use it before broad repository discovery when the code location is unknown.
- `knowledge_search`: **what durable facts/invariants are already known?** Searches reviewed Project Knowledge. Call it when those facts can materially affect the task, not mechanically on every request.
- `decision_search`: **why was a consequential choice made?** Search before revisiting architecture/API/provider/migration/concurrency/security/persistence choices with plausible alternatives.

If the user already supplied a precise file or symbol, do not call `project_search` merely for ceremony: after `project_status`, inspect that source directly. If Project Map results are stale, use them only as hints and verify current source.

A request such as "continue" must use `project_status.work.current_focus`. If a managed Task is active, continue it. Otherwise, if an Epic is executing, continue that Epic. If neither is active, treat the message as a new request rather than reconstructing old chat state by guesswork.

## Default native mode

Ordinary engineering defaults to host-native execution:

1. Call `project_status` once at the start of registered-project work.
2. If the relevant location is unknown, call `project_search` with the actual user goal before broad grep/find/repository scanning.
3. Open the strongest current-source candidates with native tools and widen exploration only when evidence requires it.
4. Let host-native skills activate by relevance. Do not preload unrelated skills.
5. Implement, test and use native subagents according to task complexity and host capabilities.
6. Record durable Project Knowledge/Decisions/Task or Epic state only when there is something worth preserving across chats and agents.

AI Layer should save tokens by reducing rediscovery. Do not spend more control-plane calls than the uncertainty they remove.

## Managed Tasks and Epics

Tasks and Epics remain first-class durable tools. They are no longer a universal permission layer.

Use a managed Task when persistent lifecycle/state, independent review, provenance, durable findings, recovery or dashboard tracking adds real value. Existing Task profiles, stages and review facilities are preserved. `task_next` is authoritative **inside an active managed Task**; it is not the mandatory navigator for every repository action.

Use an Epic for a large outcome that needs durable specification, planning, linked Tasks, integration state and human gates. `epic_next` is authoritative **inside an intentionally selected/executing Epic**. DRAFT or APPROVED Epics stay passive and do not capture unrelated work.

When `project_status` reports an active managed Task/Epic and the user asks to continue, call the corresponding navigator instead of rediscovering state.

## Strict managed Task flow

The existing strict flow is intentionally retained for work that benefits from independent execution/review boundaries, especially high-impact or explicitly managed changes.

- STANDARD normally separates IMPLEMENT → REVIEW and, when findings require changes, FIX → REVIEW.
- DISCOVERY_FIRST starts with read-only evidence gathering.
- ANALYSIS_ONLY can end without mutation.
- MICRO can use bounded inline implementation when the live Task contract grants it.
- Delegated IMPLEMENT/FIX workers are writable only for their stage. REVIEW/DISCOVERY workers remain read-only according to the live contract.
- `task_adopt` records already-existing unmanaged changes honestly instead of inventing retrospective implementation provenance.
- Review sandboxes/check tools, worker leases, findings, remediation caps and verification evidence remain available for managed flows.

Inside a managed Task, current `task_next` output wins over examples in this skill. Do not fabricate worker results, review evidence or completed checks.

## Epic lifecycle

Epic specification, versioning, audit, approval, planning, linked Tasks, drift reconciliation, intervening review and archive/completion state remain durable capabilities. Approval is still an explicit human gate. Use `epic_next` to determine the exact live action once the user selects or resumes an Epic.

An Epic can call into managed Tasks for bounded implementation. While a linked Task is active, the Task owns its internal stage lifecycle and the Epic remains the outer outcome record. Return to `epic_next` after linked Task completion or material drift.

## Dirty worktrees and recovery

A dirty worktree is valid project state. Do not stash, reset, discard, commit or rewrite user-owned changes merely to satisfy AI Layer. `project_status` reports worktree state cheaply. Managed Task creation/adoption keeps its existing baseline/provenance mechanisms when those guarantees are actually requested.

After chat/context loss, prefer durable state over narrative reconstruction: `project_status` first, then `task_next` or `epic_next` only if that state shows a managed focus. Sessions, findings, Knowledge and Decisions provide further durable recovery evidence when relevant.

## Knowledge and decisions

Project Knowledge stores reviewed semantic facts, constraints, invariants and fragile-area understanding. It is deliberately separate from Project Map. Project Map says where to inspect; Knowledge says what is already understood; Decisions say why important choices were made.

Do not store transient implementation narration or source-code copies as Project Knowledge. Source paths in Knowledge are evidence pointers, not replacement code. Changed evidence can invalidate Knowledge as stale.

## Skills

Host-native Agent Skills own relevance selection and progressive disclosure. AI Layer remains the authoritative skill package/source where configured, but it should publish skills into each host's native skill system rather than centrally deciding every skill activation.

Use `skill_get` when explicit authoritative retrieval or a specific section is needed. Do not call `skill_list` or load full skills as routine startup ceremony.

## Verification and observability

Native tests/checks remain the normal execution mechanism. AI Layer verification runners and managed review checks add durable evidence when needed. Never claim a check passed unless it actually ran.

Dashboard, Runtime Events, Task/Epic projections, skill usage and context telemetry remain observability surfaces. They describe engineering work; they should not force extra lifecycle transitions merely so the dashboard has data.

## Failure behavior

Project Intelligence is an optimization and continuity layer, so failure should be visible rather than paralyzing. If `project_status` or Project Map is temporarily unavailable, state that the reusable context/index could not be obtained and continue with host-native source inspection when safe. Never invent Task, Epic, Knowledge or Decision state.

A failure **inside an explicitly active managed Task/Epic transition** is different: preserve that durable workflow's integrity and report/block the managed transition rather than fabricating lifecycle history.

## Completion criteria

For ordinary native work, completion means the requested engineering outcome is implemented and appropriately verified. A Task is not required merely to make completion legitimate.

For managed Tasks/Epics, their own live completion/acceptance contracts remain authoritative. Preserve unresolved findings, blockers, human decisions and verification evidence in durable state rather than hiding them in prose.
