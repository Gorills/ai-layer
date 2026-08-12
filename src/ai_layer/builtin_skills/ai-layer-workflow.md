---
slug: ai-layer-workflow
description: AI Layer operating model for Project Intelligence, continuation, host-native execution, optional managed Tasks/Epics, review, recovery and durable project memory.
kind: core
keywords:
- ai layer
- project_status
- project_search
- project_map_reconcile
- knowledge_search
- decision_search
- task
- epic
- review
- recovery
entry_sections:
- Apply when
- Core contract
- Decision rules
---

# AI Layer Workflow

## Apply when

Apply this skill when working in a project registered with AI Layer and the work can benefit from reusable project state, code-location breadcrumbs, durable engineering memory, Task/Epic continuation, review evidence, or observability.

The skill is relevant at the beginning of a project-related request because the first useful question is normally not “which workflow stage may I enter?” but “what durable state already exists, and where is the relevant code likely to be?”. Start with `project_status(project_root=<workspace root>)`. That call is intentionally cheap: it restores project identity, Git/worktree summary, active managed Task, executing Epic, continuation focus, and Project Map freshness without running Task/Epic navigators or rescanning the repository.

Use this skill especially for these situations:

- the user says “continue”, “carry on”, “finish this”, or otherwise refers to work that may have started in another chat or agent session;
- the relevant implementation location is not known and broad repository discovery would otherwise be required;
- a project has durable Knowledge, Decisions, Tasks, Findings, or Epics that can prevent repeated investigation;
- a risky change benefits from independent review, durable findings, verification evidence, or a strict managed Task workflow;
- a large outcome benefits from an Epic specification, approval, linked Tasks, integration state, and reconciliation;
- the agent needs to recover safely after context loss without treating chat history as durable truth.

Do not use AI Layer mechanically when it cannot reduce uncertainty or preserve useful state. If the user already gives an exact current file or symbol, after `project_status` inspect that source directly. Do not insert `project_search`, `knowledge_search`, or Task creation merely so the control plane appears in the trace.

## Core contract

AI Layer is an engineering control plane. It is **not** a replacement agent runtime. Cursor, Codex, Claude Code, Antigravity, or another capable host owns ordinary source reads, edits, shell commands, tests, code search, model choice, and native subagents.

The persistent value supplied by AI Layer is different:

- Project Map preserves cheap navigation breadcrumbs about where code lives;
- Project Knowledge preserves reviewed semantic facts, invariants, constraints, integration knowledge, and fragile-area understanding;
- Decisions preserve consequential architectural rationale;
- Tasks and Epics preserve durable work state across chats and agents;
- verification and review facilities preserve evidence when stronger guarantees are useful;
- native Skills preserve reusable professional guidance while leaving relevance selection to the host;
- Runtime Events and Dashboard projections make the work observable to the user.

Current repository source is the final authority for implementation behavior. Project Map is a navigation index, not source truth. Project Knowledge is reviewed memory, not a replacement for current code. Decisions explain prior choices but can be revisited when current evidence justifies it. Task/Epic state describes managed work but does not globally revoke the host runtime’s normal engineering capabilities.

Project Map has two ownership layers. The scanner owns structural facts such as paths, languages, symbols, imports, routes, hashes, and other deterministic metadata. Agents may write only bounded semantic navigation enrichment through `project_map_reconcile`; they must never replace scanner-owned structure or store source bodies. Semantic enrichment is tied to the source hash it was learned from and becomes stale automatically when current source diverges.

For registered-project work, `project_status` is the first AI Layer state call. Its `work.current_focus` is the durable continuation anchor. After status, the normal default is host-native execution unless an already-active managed Task/Epic or an explicit user/agent choice requires a managed lifecycle.

## Decision rules

Use the smallest control-plane path that materially helps the task.

**If the user says “continue” or equivalent:** call `project_status`. If `work.current_focus` is an active managed Task, resume that exact Task through `task_next`. Otherwise, if the focus is an executing Epic, resume it through `epic_next`. If there is no managed focus, do not invent one from old prose; handle the user’s request as new work.

**If the exact relevant file or symbol is already known:** call `project_status`, then inspect that current source directly with native tools. `project_search` is unnecessary ceremony unless evidence shows the stated location is incomplete or wrong.

**If the code location is unknown:** call `project_search(query=<actual user goal>)` before broad `grep`, `find`, whole-repository search, or opening many files. Start with the strongest returned paths/symbols and related tests. Widen native exploration only when those candidates do not explain the behavior. Send the real query as written; Russian, English, and mixed code/domain terminology are all valid. Do not spend a separate model step translating a Russian query to English before search.

**If real work established better navigation knowledge:** after verification, call `project_map_reconcile` for only the paths actually inspected, understood, changed, or proven misleading. Do not scan unrelated areas merely to enrich the map. If no useful navigation fact was learned, do not manufacture enrichment.

**If semantic project facts can change the solution:** use `knowledge_search`. Good triggers include known invariants, fragile flows, integration contracts, deployment constraints, data rules, or previously reviewed subsystem behavior. Do not call it for every cosmetic or perfectly localized edit.

**If an architectural choice may already have rationale:** use `decision_search` before redesigning APIs, persistence, provider boundaries, migrations, concurrency behavior, authentication/authorization, or other consequential choices with plausible alternatives.

**If ordinary native execution is sufficient:** do not create a Task merely to authorize editing. Implement and verify through the host runtime. Durable recording is valuable only when the work/state will matter later.

**If stronger guarantees are worth their coordination cost:** create/select a managed Task. Examples include security-sensitive code, payments, migrations, high-risk persistence changes, concurrency fixes, complicated cross-module refactors, or work where independent review and durable findings are explicitly desired.

**If the outcome is larger than one bounded Task:** use an Epic for specification, planning, approval, linked Tasks, integration/reconciliation, and completion state. Do not use an Epic as a second implementation agent.

## Workflow

The default workflow is deliberately short:

1. Call `project_status(project_root=<canonical workspace root>)` once at the beginning of registered-project work.
2. Read the durable continuation state, worktree summary, and Project Map freshness.
3. When the location is known, inspect current source directly. When it is unknown, call `project_search` with the user’s real goal before broad discovery.
4. Use `knowledge_search` and `decision_search` only when their durable information can materially affect the implementation or investigation.
5. Let the host choose relevant native Agent Skills through its own progressive disclosure mechanism. Do not preload an unrelated skill bundle.
6. Use host-native reads, edits, shell commands, tests, code search, and subagents to do the engineering work.
7. Verify the smallest sufficient surface first, widening tests/checks when risk or evidence requires it.
8. If the work materially improved understanding of where a behavior lives, reconcile only that semantic Project Map delta. Otherwise skip it.
9. Persist durable state through its supported owner only: Decisions when consequential rationale matters; managed Task/Epic state through their live workflows; Project Knowledge authoring/publishing only through its review-gated managed flow. Ordinary native work may read Knowledge but must not claim direct VERIFIED publication.

For an active managed Task, switch from the default native workflow into that Task’s live contract. `task_next` becomes authoritative for the managed lifecycle. STANDARD normally uses IMPLEMENT → REVIEW and, when review finds actionable defects, FIX → REVIEW. DISCOVERY_FIRST begins with a read-only evidence-gathering stage. ANALYSIS_ONLY can complete without mutation. MICRO may permit bounded inline implementation when the live Task contract grants that exception.

When a meaningful managed Task reaches completion, use the completion receipt’s Project Map guidance. Reconcile only navigation facts established during that Task and pass its Task key as `source_task_key` so provenance is durable. A MICRO/cosmetic/local Task that learned nothing reusable about code location should not generate filler entries.

For an executing Epic, `epic_next` determines the durable next action. An Epic may create or resume linked managed Tasks. While a linked Task is active, the Task owns its internal stage lifecycle and the Epic remains the outer outcome/integration record. Return to the Epic after linked Task completion, drift, or intervening review as required by the live Epic contract. The final Epic Task must reconcile the materially affected Project Map scope and emit Task-linked `ProjectMapReconciled` evidence before the Epic can close; if the map was checked and already accurate, use a factual `no_changes_reason` rather than inventing content.

## Project Map writing contract

`project_map_reconcile` writes navigation memory, not architectural truth. Record only information established from current source actually inspected during the work.

Canonical semantic fields such as `purpose`, `responsibilities`, and `navigation_hints` are concise English. Preserve class, function, method, route, component, file, and other source identifiers exactly as they appear in the repository; never translate or normalize code identifiers. `domain_terms` may contain English, Russian, or other natural-language aliases when those terms are materially useful because they occur in user requests, project vocabulary, issue wording, product terminology, or the real investigation. Do not generate exhaustive translations or synonym lists merely to make the index look multilingual.

Good enrichment answers “where should the next agent inspect first?” Typical fields are compact purpose/responsibilities, useful domain terms, important current symbols, related files/tests, and a small number of navigation hints. Do not copy source bodies, long summaries, secrets, implementation prose, or speculative architecture into the map.

Correct old map entries when real work disproves them. Remove semantic enrichment that became misleading and cannot yet be replaced accurately. Source-hash mismatch makes semantic enrichment stale; stale entries remain breadcrumbs but must be verified against current source before use.

## Evidence to inspect

Prefer durable evidence over narrative reconstruction, and prefer current source over stored summaries for implementation truth.

At startup inspect the parts of `project_status` that matter to the request:

- `work.current_focus` and `work.continuation` for cross-chat continuation;
- active Task stage/findings when a managed Task is in progress;
- executing/open Epic state when an Epic may own the outcome;
- Git branch/HEAD and dirty-worktree summary so user-owned changes are not accidentally overwritten;
- Project Map freshness, semantic current/stale coverage, and changed paths so stale navigation hints are not mistaken for current truth.

When code location is unknown, inspect `project_search` results for ranked paths, matched symbols, compact structural metadata, semantic responsibilities/domain aliases, related tests, reasons, and freshness. These are breadcrumbs. Open the current source at the relevant locations before making code-truth claims.

When semantic history matters, inspect VERIFIED Project Knowledge and its evidence pointers. If a card is STALE, DRAFT, or unsupported by current evidence, do not present it as current verified truth. For architecture/history questions, inspect Decisions and then confirm assumptions against current source and configuration.

Inside a managed Task inspect the live `task_next` result, active stage, worker binding, findings, verification evidence, and actual repository delta. Inside an Epic inspect its current specification version, approval state, plan, linked Task results, review state, and drift/reconciliation evidence.

For completion claims inspect actual command/check results. A reported test, review, migration, build, or external action is not evidence that it ran.

## Implementation patterns

### Targeted discovery pattern

User asks for a behavior change but gives no file. Call `project_status`, then `project_search` using the behavior/problem statement exactly as naturally expressed. Open the top few current-source candidates and relevant tests. Follow actual imports/calls from there. This should replace repeated whole-repository orientation on established projects.

### Known-location pattern

User says “change `src/payments/service.py::create_payment`”. Call `project_status`, then inspect that source directly. Search the Project Map only if the local code reveals dependencies or ownership that are not obvious. The control plane should not cost more than the uncertainty it removes.

### Multilingual navigation pattern

A user may ask “где повторно создаётся заказ после ошибки iiko” while source identifiers are `RetryOrderProcessor` and `create_order`. Call `project_search` with the original query. Semantic embeddings and stored domain terms can bridge languages; exact identifiers remain English/code-native. When the task establishes a useful user-to-code alias such as “повторная отправка заказа” → retry-order subsystem, record that alias in `domain_terms`, while keeping canonical responsibilities concise English.

### Continuation pattern

User says “continue”. Do not infer from chat fragments. `project_status.work.current_focus` determines whether there is a Task or Epic to resume. Call its navigator once and follow the durable next action. If there is no managed focus, say nothing was active and proceed from the current user request.

### Durable-knowledge pattern

During real investigation, the agent establishes a non-obvious invariant such as “retry processing must remain idempotent by provider event id” and verifies it against source/tests. If the current work is inside a supported managed Knowledge author/review flow, draft it with precise evidence paths so an independent review can publish it. During ordinary unmanaged host-native work, do not pretend VERIFIED Knowledge can be written directly; create/use an explicit managed Knowledge/onboarding task when durable publication is actually valuable. Do not put behavioral invariants into Project Map merely because they mention a useful file.

### Strict managed Task pattern

For high-risk work, create/select the managed Task and obey its live profile. Delegated IMPLEMENT/FIX workers own writable stage mutations; REVIEW/DISCOVERY workers remain read-only where required. Keep worker results honest: the coordinator may record returned evidence but must not fabricate a worker execution. Use findings and re-review when defects are actionable. The remediation cap and human-attention state are safeguards against endless self-repair loops.

### Epic pattern

For a multi-part outcome, keep the Epic specification and plan at the outcome level. Implement bounded parts through linked Tasks or native work according to the Epic contract. Do not duplicate Task stage state inside the Epic. Reconcile material implementation/spec drift explicitly instead of quietly rewriting the historical specification. In the final Task, consolidate semantic Project Map navigation for the whole materially affected Epic scope after reviewing current final source and tests; do not sweep the rest of the repository.

### Stale-index pattern

If Project Map freshness is not current, use results only to narrow likely locations, then inspect current source. Do not block safe work waiting for a background scan. Changed files should be treated with extra caution because their structural breadcrumbs or semantic enrichment may lag current contents. Semantic entries whose evidence hash no longer matches current structural source are explicitly stale and should be downweighted rather than silently treated as current.

## Verification

Verification should be proportionate to risk and based on actually executed evidence.

For ordinary host-native work, run the narrowest checks that can falsify the intended change: focused unit tests, type/lint checks, targeted integration tests, build steps, or direct behavioral validation. Expand to broader suites when the change crosses boundaries, touches shared infrastructure, or the narrow result exposes uncertainty.

For code reached through Project Map, confirm that the selected current source really owns the behavior before editing. A high semantic search score is not proof of runtime ownership.

Before writing Project Map enrichment, verify every referenced path exists in the current structural map and every `important_symbols` entry is a current scanner-known source symbol. Related tests/files must be current project paths. If evidence is insufficient, omit the field rather than guess.

When a supported managed flow authors Project Knowledge, verify important claims against current source, tests, configuration, or other authoritative project evidence before drafting/reviewing durable cards. Evidence paths are pointers that make future staleness detectable. Ordinary unmanaged work should use `knowledge_search` for reads and must not fabricate direct publication authority.

For managed Tasks, preserve the existing verification runner, review sandbox, findings, review rounds, and stage evidence where the Task contract requires them. REVIEW is independent when the profile says it is independent. Do not turn a failing review into `pass` simply to close the Task. FIX must address actionable findings and then return to REVIEW when required.

For Epics, verify linked Task outcomes against Epic acceptance criteria and integration state before completion. Epic completion should not be inferred merely because all child Tasks are individually closed if the combined outcome is still inconsistent. Final closure requires durable Project Map reconciliation evidence in addition to the existing documentation and Project Knowledge evidence.

Never claim “tests pass”, “migration works”, “review passed”, or “deployment succeeded” without an actual result. Host-hidden model selection, token counts, and billing are also not verified facts unless the host exposes them.

## Failure modes

**Project status unavailable:** disclose that durable project state could not be retrieved. Do not invent active Tasks/Epics. For ordinary work, continue with safe host-native source inspection when possible. A control-plane outage should not automatically make the coding host unusable.

**Project Map unavailable or stale:** fall back to targeted native source search. Treat stale breadcrumbs as hints only. Do not wait indefinitely for scanner freshness and do not quote stored metadata as current code truth.

**Search returns weak/irrelevant matches:** widen query wording, use exact domain identifiers discovered from the first source, or fall back to host-native search. Project Map is an optimization, not a requirement to trust bad retrieval. When work discovers the correct location, reconcile that semantic breadcrumb instead of adding a separate learning pipeline.

**Project Map reconciliation rejected:** inspect the current structural map/source. Do not bypass validation or write the database directly. Common reasons are nonexistent paths, stale/unknown symbols, non-test paths supplied as tests, oversized content, or canonical semantic prose written in a non-English language. Put useful non-English search vocabulary in `domain_terms`.

**Dirty worktree:** preserve user-owned changes. Do not automatically stash, reset, discard, commit, or rewrite them. In ordinary native mode, work carefully around current changes. In a managed Task, use the existing adoption/baseline/provenance mechanisms when those guarantees are required.

**Managed stage worker fails/disconnects:** preserve the Task’s durable integrity. Do not fabricate stage evidence or silently execute a delegated strict stage under another identity. Use the Task’s recovery/blocking mechanisms.

**Managed Task navigator/transition fails:** this is different from Project Map failure. The Task lifecycle is durable state, so do not guess a transition or write a contradictory stage result. Report/block and recover through durable Task state.

**Epic drift or transition failure:** use Epic reconciliation/review mechanisms. Never rewrite approved specification history merely to match accidental implementation drift.

**Knowledge conflict:** current source and authoritative configuration beat an old card. Mark/update the durable knowledge through its review process rather than forcing source to match memory.

**Excessive ceremony:** if control-plane calls, stages, or subagents are not reducing uncertainty or increasing required assurance, simplify. Token economy is measured by total cost to an accepted result, not by maximizing protocol activity.

## Related skills and escalation

Normal domain guidance should come from host-native Agent Skills. Let the host select backend, database, security, testing, frontend, Docker, framework, design, accessibility, or other relevant skills from the synchronized catalog. Do not call `skill_list` and manually load every plausible skill at startup.

Use `skill_get` when an authoritative AI Layer skill body/section is explicitly needed or host-native activation is insufficient. Keep progressive disclosure: load the smallest relevant professional guidance first, then request deeper material only when necessary.

Escalate from default native execution to a managed Task when the work needs durable lifecycle guarantees, independent review, provenance, durable findings, or recoverable stage state. Escalate to a stronger/strict profile for high-risk security, authorization, payments, migrations, destructive data changes, concurrency, critical integrations, or similarly consequential work.

Escalate from a Task to an Epic when the requested outcome contains multiple coordinated deliverables, a durable specification/approval boundary, several linked Tasks, or integration/reconciliation work that should outlive one implementation session.

Escalate to the user when a managed remediation cap is reached, requirements materially conflict, a destructive choice needs authorization, or evidence cannot safely resolve a consequential ambiguity. Do not use “human attention” as a substitute for ordinary engineering judgment when the evidence is sufficient.

## Project intelligence and durable memory

Project Map, Knowledge, Decisions, Tasks, and Epics intentionally solve different problems and should remain separate.

Project Map answers **where to inspect** and has two layers: deterministic scanner-owned structure plus bounded agent-authored semantic breadcrumbs learned during real work. Knowledge answers **what durable reviewed facts matter** and can be sparse. Decisions answer **why a consequential choice was made**. Tasks/Epics answer **what work is active and what durable lifecycle state exists**.

Do not collapse these into one giant startup payload. A large mandatory `memory_context` recreates the same token overhead Project Intelligence is meant to avoid. Retrieve status first, then only the specific type of context required by the task.

The desired economic effect is amortization: an agent investigates a subsystem once, useful map/knowledge/decision state survives, and later agents begin at a small set of likely current-source locations instead of repeatedly scanning the repository from scratch. Project Map enrichment should therefore harvest knowledge from work that already happened, not launch a duplicate repository-analysis agent after every Task.

## Observability

Dashboard and Runtime Events should describe useful engineering activity, not manufacture it. Project pages may show current focus, Task stages/findings, Epics, Project Map structural size, semantic current/stale coverage, Knowledge, Skills, agents, verification, and protocol/runtime telemetry.

Do not add workflow transitions merely to make the dashboard richer. Observability is a read-side projection of real work. When model/token/cost data is host-hidden, label it as requested, estimated, or unverified rather than presenting it as measured billing truth.

Project Intelligence calls should remain bounded and auditable so future A/B evaluation can compare native-only work with AI Layer-assisted work using first-edit latency, discovery breadth, model turns, actual host token/cost data where available, verification failures, user corrections, accepted-result quality, Project Map zero-hit rate, semantic hit rate, and whether top results were actually useful to subsequent source inspection.

## Completion criteria

Ordinary host-native work is complete when the requested engineering outcome is implemented, relevant current source has been inspected, and proportionate verification has actually passed. A managed Task is not required merely to legitimize completion. If meaningful navigation knowledge was learned during substantial work, reconcile that bounded Project Map delta before handoff; trivial work may skip it.

Project Intelligence use is successful when it reduced or correctly avoided repository discovery without causing the agent to trust stale metadata over current source. Durable Knowledge/Decisions should be recorded only when they will plausibly save future investigation or preserve an important constraint/rationale.

A managed Task is complete only according to its live acceptance/stage/review contract. Preserve unresolved findings and blockers rather than hiding them in prose. Its completion receipt may request a bounded Project Map reconciliation after meaningful work. An Epic is complete only when its approved outcome and integration criteria are satisfied and its final Task has produced documentation, Project Knowledge, and Project Map reconciliation evidence.

Before finalizing, ensure no user-owned work was discarded, no test/review result was invented, no stale Project Map/Knowledge claim was treated as current source truth, no semantic map entry was guessed or bloated with exhaustive translations, and no unnecessary control-plane ceremony was added where native execution was already sufficient.
