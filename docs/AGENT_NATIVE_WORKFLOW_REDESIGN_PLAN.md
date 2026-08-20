# Agent-Native Workflow Redesign Plan

## Status

**Planning branch:** `redesign/agent-native-workflow`

**Target:** a staged redesign of AI Layer's agent-facing workflow, Project Intelligence, observability, and Dashboard experience.

**Implementation status:** plan only; no behavior in this document should be treated as implemented until the corresponding phase is completed and verified.
**Authority:** current source, migrations, tests, accepted ADRs, and executable gates remain authoritative until an ADR and implementation explicitly supersede them.

This plan intentionally does **not** modify `PRODUCT_GOAL.md`, `ROADMAP.md`, `ARCHITECTURE.md`, or accepted ADRs yet. Those are canonical documents and should be changed only when the new contracts are accepted and executable.

---

## 1. Why this redesign exists

AI Layer's product idea remains sound:

- a human should see durable work across many projects without reconstructing chat history;
- an agent should enter an old or unfamiliar project and recover useful context quickly;
- Project Map, reviewed Project Knowledge, Decisions, Skills, and prior work should reduce rediscovery;
- stronger review, verification, recovery, and planning should be available when the work benefits from them;
- the host coding agent should remain the execution engine rather than being replaced by another agent loop.

The practical failure is at the **interaction boundary**.

Today the system still exposes too much of its internal workflow model to the model. Even though recent work has already removed some duplicated procedure and automatically creates/links backing Work for managed Tasks, an agent is still expected to understand a broad catalog containing Work, Task, Epic, stage, delegation, review, verification, Project Map, Knowledge, Skills, session, and worker-control operations. The system then relies on bootstrap prose and skills to make a probabilistic model choose and sequence those operations correctly.

That has three negative effects:

1. **Workflow ceremony competes with engineering.** The agent spends reasoning/tool turns navigating AI Layer instead of solving the user's problem.
2. **The happy path is not naturally attractive.** Native grep/read/edit/test is often easier than deciding which Project Intelligence/workflow tools to call, so agents bypass the control plane unless instructed aggressively.
3. **Human-visible state depends too much on agent discipline.** Missing or incorrectly sequenced calls can make the Dashboard incomplete even when useful engineering work occurred.

The redesign goal is therefore not "fewer rules" by itself. The goal is:

> **Move procedure from prompt instructions into server-owned state transitions, while making the remaining agent-facing calls provide obvious immediate engineering value.**

The correct path must become the shortest path.

---

## 2. Verified starting point and constraints

The redesign must start from the current architecture, not from an imagined clean slate.

### 2.1 Useful foundations that must be preserved

The current repository already contains important pieces we should reuse:

- `WorkItem` is a durable user-visible unit independent from managed Task assurance (`src/ai_layer/db/work_models.py`).
- `AgentRun` and `RuntimeEventContext` provide a correlation spine for human-visible work and observed runtime activity.
- managed Task creation already creates or links backing Work inside the application layer (`src/ai_layer/application/managed_work.py`, `src/ai_layer/application/tasks.py`); the agent is not supposed to maintain that link manually.
- PostgreSQL is already the canonical authority for managed workflow state and critical concurrency.
- Task stage semantics, review/fix loops, findings, verification, worker provenance, review sandboxes, and recovery are valuable and should not be weakened.
- Epic orchestration is already separated from Task stage ownership.
- Project Map separates deterministic scanner-owned structure from source-hash-bound semantic breadcrumbs.
- Project Knowledge is evidence-backed, review-gated, and separate from current source.
- Dashboard has already moved toward project/outcome-oriented views instead of raw entity catalogs.
- response-envelope work has already removed large repeated procedure essays from many MCP responses.
- the host remains the native source/read/edit/shell/test/subagent execution owner.

### 2.2 Current seams that create friction

The following current surfaces are specifically in scope for redesign:

- `src/ai_layer/domain/agent_contract.py`
- `src/ai_layer/domain/orchestrator.py`
- `src/ai_layer/mcp/server.py`
- `src/ai_layer/mcp/tools/work.py`
- `src/ai_layer/mcp/tools/tasks.py`
- `src/ai_layer/mcp/tools/epics.py`
- `src/ai_layer/mcp/tools/project_context.py`
- `src/ai_layer/application/project_intelligence.py`
- `src/ai_layer/application/managed_work.py`
- `src/ai_layer/application/tasks.py`
- `src/ai_layer/application/epic_*`
- `src/ai_layer/memory/project_map_*`
- `src/ai_layer/application/knowledge.py`
- `src/ai_layer/builtin_skills/ai-layer-workflow.md`
- host integration/bootstrap delivery
- Work/Task/Epic Dashboard projections

### 2.3 Accepted decisions that will need explicit treatment

This redesign is large enough that some accepted decisions will need to be **preserved, revised, or superseded explicitly**, not silently bypassed.

At minimum, implementation must review:

- ADR 0017 — Project Intelligence control plane;
- ADR 0018 — agent-maintained semantic Project Map;
- ADR 0019 — live agent contract and semantic governance;
- ADR 0020 — durable Work spine and truthful observability;
- ADR 0025 — MCP response envelopes.

In particular, ADR 0025 currently says the MCP tool catalog remains unfiltered. A new default agent façade with a deliberately small catalog would change that contract and therefore requires a new ADR plus regression tests before becoming default.

---

## 3. Product north star

### 3.1 Human experience

The human should think in terms of **projects and outcomes**, not Work/Task/Epic mechanics.

A normal project view should answer:

- What is being worked on now?
- What is blocked or waiting for me?
- What finished recently?
- What changed?
- What checks/review happened?
- How trustworthy is the result?
- What did AI Layer learn that will make later work faster?

A representative card:

```text
Fix duplicate webhook delivery
Review passed
3 files changed · focused tests passed
Independent review · Project Map updated
Completed 18 Aug
```

Technical details may reveal `W-*`, `T-*`, `E-*`, stages, workers, leases, verification IDs, and raw event correlation, but those are drill-down information.

### 3.2 Agent experience

The agent should think:

```text
1. Enter the project/outcome.
2. Receive a useful brief and one current action.
3. Use native tools to do engineering.
4. Report genuinely new facts/results.
5. Repeat only if the server returns another required action.
6. Finish the outcome.
```

The agent should **not** need to know how to:

- create or link backing Work;
- decide which internal stage row must exist;
- maintain Task/Work/Epic linkage;
- translate a Task stage transition into a sequence of MCP bookkeeping calls;
- update Dashboard state;
- correlate RuntimeEvents;
- decide whether a completed stage implies another Task poll;
- carry durable IDs that the server can derive from an action token/session binding;
- manually reconcile structural map facts that the scanner can derive.

### 3.3 Core product invariant

> **Agents report user intent and genuinely new engineering facts. AI Layer owns workflow mechanics, durable linkage, correlation, transition creation, and projection.**

---

## 4. Non-negotiable invariants

The redesign is not allowed to "simplify" by throwing away guarantees.

1. **Source truth stays native.** Current repository source is authoritative.
2. **No new agent runtime.** AI Layer does not take over the model/tool loop of Codex, Claude Code, Cursor, Antigravity, or another host.
3. **Dirty worktrees remain valid user state.** No implicit stash/reset/restore/commit.
4. **Managed assurance remains real.** Independent review cannot be replaced by the same actor reporting "reviewed".
5. **Task/Epic transitions remain database-authoritative and concurrency-safe.**
6. **Dashboard reads remain read-only.**
7. **No source bodies, hidden reasoning, raw prompts, or secrets enter durable human history by default.**
8. **Project Map remains navigation, not behavioral truth.**
9. **Project Knowledge remains reviewed evidence-backed semantic memory.**
10. **Observed/reported/inferred assurance classes stay explicit.**
11. **Failures in Project Intelligence remain fail-soft for safe host-native engineering.**
12. **Compatibility is removed only after field evidence proves the new path.**
13. **No big-bang destructive migration.**
14. **Every new abstraction must reduce net agent/user complexity.**

---

## 5. Target architecture

```text
                         HUMAN
                           |
                    Portfolio / Project UI
                           |
                    User-visible Outcomes
                           |
        +------------------+------------------+
        |                  |                  |
 Project Intelligence   Durable Work       Assurance
        |                  |                  |
 Map / Knowledge        WorkItem tree       Task FSM
 Decisions / stack      AgentRun            Epic plan
 Retrieval evidence     RuntimeEvent        Review/Fix
        |                  |                  |
        +------------------+------------------+
                           |
                  Agent-facing façade
                           |
         +-----------------+-----------------+
         |                 |                 |
    project_enter     project_lookup    work_continue
                                             |
                                        work_finish
                           |
                    HOST CODING AGENT
                           |
                 native read/edit/test/subagents
```

The rich internal capability model remains. The change is the public protocol.

### 5.1 Design lessons from agent harnesses

DeepSeek Harness and similar agent runtimes are useful here mainly as a boundary lesson, not as a product template to copy.

They keep the model/tool execution loop narrow and move policy, persistence, tool execution, subagents, and other behavior behind explicit runtime seams. AI Layer should apply the same principle one level above the host runtime:

- keep the **agent-visible control-plane loop** narrow;
- keep Task/Epic/verification/retrieval capabilities composable behind it;
- persist durable facts/events so continuation is reconstructable;
- return the exact current action rather than asking the model to infer procedure;
- do not reimplement the host's model/tool loop.

The redesign should borrow these composability/state-ownership ideas without turning AI Layer into another coding-agent harness.

---

## 6. Canonical domain model after redesign

### 6.1 WorkItem becomes the universal human outcome anchor

`WorkItem` remains the durable user-visible identity.

Every substantive outcome visible in the Dashboard has a Work identity regardless of whether it is:

- native/unmanaged engineering;
- managed with Task assurance;
- promoted into a planned Epic;
- resumed after a week;
- split into planned sub-outcomes.

### 6.2 Managed Task becomes an assurance attachment

A Task is not "another user job". It is the internal assurance state machine attached to a bounded Work unit.

This redesign does **not** automatically relax the existing one-open-managed-Task-per-project constraint. Preserve that invariant during the protocol/domain migration; revisit managed parallelism only as a separate evidence-driven change if real usage requires it.

Target relation:

```text
WorkItem 1 ---- 0..1 active ManagedTask
```

Historical Tasks may remain associated, but one bounded Work unit has one current assurance flow at a time.

Promotion:

```text
native Work
   |
   | same Work identity
   v
managed Work (Task attached)
```

No new top-level human work card is created merely because assurance was attached.

### 6.3 Epic becomes planning/orchestration attached to a root outcome

An Epic is the planning/integration state of a larger root Work outcome.

```text
Root Work
   |
   +---- Epic
           |
           +---- Child Work A ---- optional Task
           +---- Child Work B ---- optional Task
           +---- Child Work C ---- optional Task
```

This makes human history coherent:

- the root outcome is what the human asked for;
- the Epic describes how it was decomposed;
- child Work units are independently meaningful deliverables;
- each child can use native or managed assurance;
- internal Task creation must not manufacture duplicate portfolio Work rows.

### 6.4 Required persistence evolution

Do not immediately delete `linked_task_id` / `linked_epic_id`.

Use additive migration first. Preferred target:

- explicit canonical Work association from Task;
- explicit canonical root Work association from Epic;
- parent/root relationship for child Work created by Epic planning;
- constraints preventing one Task from silently belonging to multiple unrelated Work outcomes;
- migration/backfill from current `WorkItem.linked_task_id` and `linked_epic_id`;
- dual-read compatibility until all read models use the new canonical association.

Exact column/link-table choice must be decided after inspecting migration/concurrency impacts in the dedicated persistence phase.

---

## 7. New agent-facing protocol

The exact names are provisional until Phase 1 contract testing, but the **shape** is the target.

Default agent-facing MCP should expose a deliberately small façade. Internal/admin/compatibility capabilities remain available through application APIs, Dashboard HTTP, CLI, or an opt-in legacy MCP server.

### 7.1 `project_enter`

Purpose: one natural entry point for start/resume/status + useful initial Project Intelligence.

`assurance=auto` must **not** become an opaque LLM classifier that invents workflow ceremony. Its default interpretation is native execution unless one of these concrete conditions applies:

- the user explicitly requested reviewed/standard/planned work;
- current durable focus is already managed/planned;
- project policy requires a minimum assurance for a concrete affected scope;
- the agent reports a newly discovered concrete risk/scope fact and requests escalation;
- the server returns a human decision because the reported scope requires planning.

AI Layer may recommend escalation from observed/reported facts, but it must not silently create an Epic or expensive review workflow from a speculative semantic risk score.

Inputs should be bounded:

```text
project_root
goal?                 # bounded semantic goal, not raw prompt history
intent = auto|start|resume|inspect
assurance = auto|native|reviewed|planned
host/session metadata when observable
```

Responsibilities:

- resolve project identity;
- recover current focus when resuming;
- create Work when starting substantive work;
- atomically create/attach Task if `reviewed` assurance is explicitly selected;
- create/attach Epic draft/planning state only when planned work is explicitly selected or accepted;
- start/correlate AgentRun where supported;
- build a compact initial Project Brief;
- return one current action.

Typical native response:

```json
{
  "work": {"key": "W-0042", "goal": "..."},
  "mode": "native",
  "brief": {
    "stack": ["Python", "FastAPI", "PostgreSQL"],
    "likely_paths": [...],
    "related_tests": [...],
    "knowledge": [...],
    "decisions": [...]
  },
  "action": {
    "kind": "native_engineering",
    "message": "Inspect current source and implement the requested outcome."
  }
}
```

Typical STANDARD response:

```json
{
  "work": {"key": "W-0042", "goal": "..."},
  "mode": "reviewed",
  "action": {
    "kind": "run_worker",
    "action_token": "...",
    "role": "implement",
    "worker_spec": {...}
  }
}
```

### 7.2 `project_lookup`

Purpose: make AI Layer materially better than blind broad search.

It replaces routine model-level decisions between `project_search`, `knowledge_search`, and `decision_search`.

Inputs:

```text
project_root
work/action binding when available
query
scope? / exact identifiers?
limit
```

Server performs bounded fusion:

- structural Project Map search;
- semantic map search;
- relevant tests/files expansion;
- VERIFIED Knowledge retrieval;
- relevant Decisions when confidence/relevance warrants it;
- freshness/staleness annotations;
- stack/project-profile facts if useful.

Response is an **engineering navigation packet**, not three separate search dumps.

The old focused search APIs may remain internal/legacy for diagnostics and compatibility.

### 7.3 `work_continue`

Purpose: one transition boundary for genuinely new facts/results.

It accepts a typed report associated with the current Work/action token.

Report kinds may include:

- native progress/blocker;
- worker result;
- review findings/verdict;
- verification evidence summary;
- discovered scope/risk requiring stronger assurance;
- human decision;
- plan/reconciliation result.

The server must:

1. validate the action token/state version;
2. persist the report and safe evidence;
3. close/advance the current internal Task/Epic stage if applicable;
4. bind/create the next worker/stage atomically when needed;
5. update Work/Task/Epic correlation and events;
6. return the **next action in the same response**.

This removes the current pattern:

```text
complete stage
-> task_next
-> task_stage_delegate
-> start worker
```

The target is:

```text
work_continue(worker_result)
-> server advances + binds
-> returns next run_worker action
```

### 7.4 `work_finish`

Purpose: terminalize the user outcome.

It records only facts the control plane cannot reliably derive:

- bounded result summary;
- reviewed/changed paths when host observation cannot supply them;
- checks when host hooks cannot supply them;
- terminal outcome;
- unresolved blocker/failure reason when applicable.

Server derives:

- repository delta where safely observable;
- Work/Task/Epic final linkage;
- AgentRun termination;
- Project Map retrieval effectiveness;
- map learning disposition;
- durable events/projections.

### 7.5 `work_next` or resume via `project_enter`

A separate `work_next` should exist only if it proves useful for context-loss recovery. Prefer `project_enter(intent=resume)` if that keeps the public surface smaller without making schemas ambiguous.

The invariant is more important than the exact name:

> one call restores the current server-owned action; the model never reconstructs the Task/Epic FSM from prose.

### 7.6 Compatibility surface

Current fine-grained tools remain available during migration, but not in the default agent catalog once the façade is proven.

Candidate split:

```text
ai-layer-mcp          -> new small agent façade (default)
ai-layer-mcp-legacy   -> current broad catalog (opt-in compatibility/debug)
```

Do not switch installer defaults until field acceptance passes.

---

## 8. Natural lifecycle flows

### 8.1 Ordinary work

```text
User: "Fix duplicate webhook delivery"

project_enter(goal=..., assurance=auto)
  -> Work W-42
  -> compact brief
  -> native_engineering

host-native inspect/edit/test

work_finish(...)
  -> completed
  -> dashboard/event closure
  -> retrieval/learning evaluation
```

Target model-facing control-plane calls on the happy path: **2**.

`project_lookup` is optional and used because it is useful, not mandatory.

### 8.2 Explicit STANDARD/reviewed work

```text
User: "Do this with the standard reviewed workflow"

project_enter(goal=..., assurance=reviewed)
  -> atomically creates Work + Task + IMPLEMENT binding
  -> run_worker(IMPLEMENT)

host runs worker

work_continue(implement_result, action_token)
  -> records IMPLEMENT
  -> atomically creates/binds REVIEW
  -> run_worker(REVIEW)

host runs reviewer

work_continue(review_result, action_token)
  -> PASS => done action
  -> or findings => atomically creates/binds FIX

...

work_finish(...)
```

The parent agent never calls `task_create`, `task_next`, `task_stage_delegate`, `task_implementation_complete`, and then `task_next` as separate procedural steps.

Those capabilities remain internal implementation owners.

When a host exposes subagent/session identity, the returned `run_worker` action should bind the expected worker run and `work_continue` should correlate the actual result to that run. On hosts without such hooks, the weaker provenance must remain explicitly labelled rather than being upgraded by assertion.

### 8.3 Native work naturally escalates to reviewed work

Initial work begins native.

During source inspection the agent discovers concrete risk:

- migration;
- payment/authorization boundary;
- concurrency semantics;
- cross-service behavior;
- broad unexpected delta;
- project policy requiring review.

Agent reports the **fact**, not "create Task T-*":

```text
work_continue(
  report = {
    kind: "risk_discovered",
    reason: "...",
    requested_assurance: "reviewed"
  }
)
```

AI Layer:

- keeps the same Work identity;
- captures pre-managed delta as provenance;
- attaches/adopts managed Task state using the existing adoption semantics;
- chooses the correct next managed action from actual repository state;
- returns the reviewer/implementer action.

### 8.4 Work naturally promotes to an Epic

The agent discovers that the outcome contains multiple independently verifiable deliverables.

It reports:

```text
kind = "scope_expanded"
deliverables = [...]
risks/dependencies = [...]
```

AI Layer may return:

```text
action.kind = "human_decision"
recommendation = "promote_to_plan"
```

On user acceptance:

- the same Work remains root outcome;
- Epic is attached;
- plan items create child Work only for independently meaningful deliverables;
- child Work may attach Tasks based on required assurance.

No duplicate root card is created.

### 8.5 Continue after a week

```text
User: "Continue"

project_enter(intent=resume)
  -> finds exact durable root Work
  -> returns current brief + current action
```

No dependence on chat transcript.

### 8.6 Context/process restart during managed work

The live action is persisted with state/version identity.

After restart:

```text
project_enter(intent=resume)
```

returns the same or safely recovered action.

Duplicate `work_continue` delivery is idempotent. Stale action tokens fail with a precise "refresh current action" response and do not repeat side effects.

---

## 9. Project Intelligence must become an advantage, not an obligation

The most important acceptance criterion for Project Map/Knowledge is not "the agent called it".

It is:

> **Did the call reduce the number of native discovery steps and improve the probability of inspecting the right files first?**

### 9.1 Project Brief

`project_enter` should return a small brief assembled from existing durable data.

Candidate fields:

- project stack/runtime/framework signals;
- likely entrypoints;
- top relevant implementation paths;
- related tests;
- high-confidence semantic responsibilities;
- 1-3 relevant VERIFIED Knowledge facts;
- highly relevant prior Decision(s);
- freshness/staleness warnings;
- current worktree branch/dirty summary when relevant.

The brief must be capped by production constants and ranked by usefulness.

Do not return:

- generic architecture essays;
- raw source;
- unrelated Knowledge cards;
- exhaustive route/import lists;
- internal scanner diagnostics;
- histories that cannot change the next action.

### 9.2 Hybrid retrieval pipeline

`project_lookup` should use existing structural + semantic Map search but add a bounded fusion/reranking layer.

Target sequence:

```text
goal/query
  -> normalize only natural-language retrieval terms
  -> preserve exact identifiers verbatim
  -> lexical structural candidates
  -> semantic Map candidates
  -> graph/relationship expansion from top candidates
       imports/call ownership where available
       related tests
       routes/config/persistence evidence
  -> Knowledge candidates
  -> Decisions candidates
  -> confidence/freshness/risk weighting
  -> compact ranked packet
```

Do not build a second source index containing source bodies.

### 9.3 Retrieval telemetry and implicit feedback

Every brief/lookup should receive a durable `retrieval_id` with safe metadata:

- query fingerprint / bounded normalized terms;
- candidate paths;
- ranking scores/reasons;
- freshness state;
- source channels used;
- latency/payload size.

When the Work later records actual reviewed/changed paths, AI Layer can compare them with the suggested candidates.

Useful metrics:

- top-1 / top-3 / top-5 path hit rate;
- related-test hit rate;
- fraction of work that immediately widened to broad native search;
- stale-result correction rate;
- time/calls from project entry to first relevant source read;
- time/calls to first correct edit;
- retrieval candidates ignored vs used.

This creates a measurable self-improvement loop without claiming the model "understood" a delivered result.

### 9.4 Semantic Map learning from real work

Routine users should not have to remember `project_map_reconcile`.

At Work completion, AI Layer already has or can receive:

- actual reviewed paths;
- changed paths;
- retrieval candidates;
- task findings;
- safe result summary;
- source hashes.

The system should derive the **reconciliation opportunity** automatically.

Structural changes remain scanner-owned.

For semantic breadcrumbs:

- accept bounded semantic observations already present in the work result;
- validate paths/symbols against current structural map;
- bind them to current source hash;
- update only affected entries;
- record provenance from the Work/Task;
- never manufacture prose only to satisfy a completion gate.

A manual/admin reconcile tool may remain, but routine completion should not depend on a separate model-facing reconciliation call.

---

## 10. Project Knowledge must help without becoming another ceremony

### 10.1 Retrieval

Relevant VERIFIED Knowledge should normally be included in `project_enter` / `project_lookup` automatically.

The agent should call a dedicated Knowledge tool only for deep/explicit Knowledge inspection, not as routine startup procedure.

Ranking should combine:

- semantic relevance to the goal;
- path overlap with current Map candidates;
- subsystem/category relevance;
- freshness;
- historical usefulness;
- explicit fragile-area/invariant priority.

### 10.2 Learning

Do **not** weaken VERIFIED Knowledge publication.

Instead separate:

```text
candidate observation
      |
      v
DRAFT knowledge candidate
      |
 independent evidence review
      |
      v
VERIFIED
```

Ordinary Work may produce **candidate** durable facts from already-reported engineering results without pretending they are VERIFIED.

Possible sources:

- agent-reported non-obvious invariant with evidence paths;
- repeated corrected Project Map semantics;
- review finding that reveals a fragile contract;
- explicit human architectural decision.

Publication remains review-gated.

### 10.3 Avoid per-work review tax

Do not force every useful knowledge candidate to launch a Task.

Options to evaluate in implementation:

1. attach candidates to the next already-required independent REVIEW;
2. batch project Knowledge candidates into a dedicated maintenance review;
3. allow explicit human approval for low-risk metadata classes if policy permits;
4. keep high-impact invariants under independent managed review.

The exact policy needs an ADR because current Knowledge write semantics are strongly coupled to managed Task review.

---

## 11. Agent Skills after the façade exists

Do not start by shortening instructions. That was tried conceptually and cannot solve a procedural API.

After the façade is working:

- replace the always-on workflow procedure with a very small invariant set;
- keep domain/professional Skills host-native;
- keep detailed managed recovery procedure server-side;
- shrink or repurpose `ai-layer-workflow.md` so it is not a manual for operating internal state machines.

Target always-on contract:

```text
1. Enter registered project work through AI Layer.
2. Use the returned Project Brief when useful, but verify current source.
3. If AI Layer returns a required action token, execute that action and report its real result.
4. Never fabricate evidence or destroy user worktree state.
```

Weak-agent reliability must be tested with the **small contract + constrained façade**, not assumed.

---

## 12. Enforcement model: what can actually be guaranteed

AI Layer does not own the host model loop, so there are two classes of guarantee.

### 12.1 Server-enforceable guarantees

These must move out of prose wherever possible:

- valid transition order;
- worker binding before managed mutation;
- read-only review/discovery requirements;
- stale action rejection;
- independent reviewer identity;
- remediation limits;
- verification evidence ownership;
- Work/Task/Epic linkage;
- idempotency;
- concurrency;
- human approval gates;
- Epic/Task ownership boundaries.

### 12.2 Host-dependent behavioral conventions

These cannot be guaranteed solely by AI Layer:

- whether a host calls AI Layer at all;
- whether it cognitively uses a Project Brief;
- whether a host truly used a native skill;
- exact model/prompt/token billing;
- exact native source reads when host exposes no hook.

The product response is not more prompt threats.

Instead:

- make the façade useful enough to be chosen;
- use official host lifecycle/tool/subagent hooks when available;
- observe what can be observed;
- label unsupported coverage honestly;
- retain a tiny bootstrap entry invariant.

---

## 13. Observability that does not depend on bookkeeping calls

### 13.1 Agent reports only semantics

Agent-reported fields should be limited to things AI Layer cannot safely derive:

- goal;
- meaningful result;
- blocker;
- risk/scope discovery;
- review finding/verdict;
- human decision;
- non-observable verification result;
- semantic learning observation.

### 13.2 Host adapters derive mechanics

Where official hooks exist, adapters should capture:

- session/run lifecycle;
- subagent lifecycle;
- tool/check lifecycle;
- timestamps;
- stable host/session/turn identity;
- changed paths or repository delta;
- terminal host run state.

Do not claim more than the host exposes.

### 13.3 Fallback observation

For hosts without hooks:

- MCP correlation;
- repository snapshots/deltas;
- Git state;
- control-plane events;
- agent-reported summaries

may produce partial evidence, explicitly labelled with the existing assurance/coverage vocabulary.

### 13.4 Dashboard must tolerate missing agent calls

A missed optional progress report must not erase evidence that the host adapter observed a run and repository delta.

Conversely, observed file changes must not invent a user goal or attribute them to an agent without evidence.

---

## 14. Outcome-centric Dashboard

The Dashboard should keep internal models distinct but present them through an outcome-centric projection.

### 14.1 Portfolio

Default hierarchy:

1. Needs attention
2. Active outcomes
3. Recently completed
4. Projects
5. System/runtime health

### 14.2 Project workspace

Primary Work/Outcome card shows:

- goal/title;
- current human state;
- live/awaiting/blocked/completed;
- current execution mode: native/reviewed/planned;
- assurance badge;
- current action if human attention is required;
- changed/reviewed paths;
- checks;
- review result/findings count;
- Project Intelligence learning status;
- last meaningful milestone.

### 14.3 Technical detail

Expose internal identifiers only in drill-down:

- Work key;
- Task/Epic IDs;
- stages/workers;
- action tokens/state versions;
- RuntimeEvents;
- coverage/assurance;
- migration/debug metadata.

### 14.4 Epic presentation

Show one root outcome with plan progress:

```text
Subscription redesign
3 / 7 deliverables complete
2 reviewed · 1 blocked · 4 pending
```

Do not show an unrelated pile of backing Work rows generated by internal Tasks.

---

## 15. Agent-effort and context budgets

Before changing protocol, measure current reality. Then make these budgets release gates/acceptance targets where evidence supports them.

### 15.1 Measure

For representative journeys and each supported host:

- number of configured model-facing MCP tools;
- serialized schema bytes;
- AI Layer bootstrap bytes;
- relevant Skill descriptor/body bytes;
- AI Layer MCP call count;
- request payload bytes;
- response payload bytes;
- estimated tokens (`ceil(bytes/4)`) clearly labelled as approximate;
- p50/p95 MCP latency;
- number of native search/read calls before first relevant source;
- number of native discovery calls before first edit;
- total engineering checks;
- duplicate control-plane calls;
- workflow correction/retry rate.

### 15.2 Initial target budgets

These are targets to validate, not release claims yet:

**Ordinary happy path**

- one `project_enter`;
- zero or more `project_lookup` only when useful;
- one `work_finish`;
- no Task/Epic tool vocabulary exposed;
- no mandatory Project Map reconciliation call.

**Reviewed happy path**

- one `project_enter`;
- one `work_continue` per actual independent actor/result boundary;
- no separate "complete -> poll -> delegate" round trips;
- one `work_finish`.

**Payload**

- each response contains only fields able to change the next action or materially reduce discovery;
- default façade schema set should be an order of magnitude easier to reason about than the current broad catalog, measured by schema bytes and tool-choice failures rather than an arbitrary exact tool count.

---

## 16. Compatibility and migration strategy

This must be an evolutionary replacement.

### 16.1 Dual protocol period

Keep current application services and current MCP tools working.

Add a new façade that initially composes those same application owners.

```text
new façade
   |
   +--> Work application services
   +--> Task application services
   +--> Epic application services
   +--> Project Intelligence
```

No duplicate Task/Epic engines.

### 16.2 Shadow mode

Before making writes authoritative through the new façade:

- run brief/lookup composition in shadow mode;
- compare suggested navigation with actual work paths;
- measure payloads/latency;
- record no user-visible behavior change.

### 16.3 Additive persistence

All schema changes are additive first.

Required migration tests:

- fresh PostgreSQL -> head;
- minimum supported schema -> head;
- current 0.14-era rows -> new relation model;
- in-flight Task with backing Work;
- Epic with linked Tasks;
- multiple active ordinary Work;
- cancelled/blocked historical state;
- legacy rows missing newer link metadata.

### 16.4 Default switch

Only after supported-host acceptance:

- installer points supported hosts at new façade by default;
- legacy MCP remains explicit opt-in;
- Dashboard reads new outcome projection;
- bootstrap switches to new invariant contract.

### 16.5 Removal

Do not delete old tools in the same release that changes default routing.

Deprecation sequence:

1. available + default old;
2. available + opt-in new;
3. new default + old opt-in;
4. old emits deprecation telemetry;
5. removal only after field evidence and migration window.

---

## 17. Detailed implementation phases

Each phase is a hard boundary. Complete, review, verify, report, then stop before starting the next phase.

### Phase 0 — Baseline and executable journey harness

**Goal:** prove where cost and failures actually occur before redesigning behavior.

Implement:

- a deterministic agent-protocol catalog report;
- schema/payload byte accounting for all MCP tools;
- journey trace format independent of raw prompts/source;
- fixtures for:
  - ordinary known-location change;
  - ordinary unknown-location change;
  - explicit STANDARD change;
  - native -> reviewed escalation;
  - continue after restart;
  - Epic continuation;
- retrieval-usefulness correlation from search candidates to actual reviewed/changed paths;
- field-run checklist for Codex, Claude Code, Cursor, and other currently supported hosts.

Verification:

- no product behavior changes;
- privacy tests prove no raw prompt/source body is required;
- baseline report generated from real current code;
- current workflow failures can be reproduced and classified.

Exit criterion:

> We can quantitatively answer where agent turns/context/tool calls are spent and how often Project Intelligence actually saves discovery.

Rollback: none; measurement-only.

---

### Phase 1 — Architecture decision and façade contract prototype

**Goal:** freeze the new boundary before deep persistence changes.

Implement/design:

- new ADR covering:
  - Work as universal outcome anchor;
  - Task as assurance attachment;
  - Epic as planning attachment/root-child Work hierarchy;
  - server-owned actions/action tokens;
  - small default agent façade;
  - compatibility server strategy;
- typed façade DTOs;
- pure contract prototype for `project_enter`, `project_lookup`, `work_continue`, `work_finish`;
- golden JSON/schema fixtures;
- no default installer switch.

Test:

- schema clarity with weak-model/tool-choice simulations;
- idempotency token shape;
- stale-action semantics;
- response size budgets;
- ambiguity cases: multiple active Work, active managed Task, new unrelated request, dirty tree.

Exit criterion:

> The public contract can express every current supported ordinary/Task/Epic journey without exposing internal FSM mechanics.

Rollback: prototype disabled; current MCP untouched.

---

### Phase 2 — Canonical Work/Task/Epic relation model

**Goal:** make promotion preserve one human outcome identity.

Implement:

- additive DB relation changes;
- migration/backfill;
- canonical application ownership for Work<->Task and root Work<->Epic;
- child Work semantics for Epic plan items;
- eliminate internal Task behavior that creates duplicate portfolio Work when a root/child Work is already known;
- read-model compatibility adapters.

Test:

- PostgreSQL race/constraint tests;
- current Task create/adopt behavior;
- Epic plan/task creation;
- blocked/cancelled/recovery cases;
- legacy data migration;
- Dashboard old projection remains truthful.

Exit criterion:

> Native -> Task and Work -> Epic promotion keep a stable user-visible Work identity.

Rollback: old fields still readable; additive schema preserved.

---

### Phase 3 — Server-owned action engine

**Goal:** remove Task/Epic procedure interpretation from the parent model.

Implement:

- persisted/derivable action state + state version;
- opaque action token bound to project/work/internal stage/version;
- façade orchestration that:
  - binds a worker atomically before returning `run_worker`;
  - accepts a real worker result;
  - records stage completion;
  - creates/binds next stage;
  - returns next action in the same transaction boundary where safe;
- recovery after duplicate/stale result delivery;
- parent no longer needs `task_next` + `task_stage_delegate` on façade path.

Preserve:

- existing Task service as semantic owner;
- worker provenance;
- read-only guards;
- review/fix semantics;
- remediation cap;
- verification/finding lifecycle.

Test:

- IMPLEMENT -> REVIEW -> DONE;
- IMPLEMENT -> REVIEW -> FIX -> REVIEW -> DONE;
- worker crash;
- duplicate result;
- stale action token;
- concurrent continue;
- dirty-tree adoption;
- restart between every transition.

Exit criterion:

> A caller can execute STANDARD using only façade actions/results and cannot accidentally skip a required managed boundary.

Rollback: façade feature flag off; fine-grained tools still work.

---

### Phase 4 — `project_enter` and Project Brief

**Goal:** make the first AI Layer call immediately useful.

Implement:

- start/resume/inspect semantics;
- atomic Work creation + optional assurance attachment;
- compact Project Brief builder;
- cached stack/runtime/project profile from deterministic evidence;
- top relevant Map candidates + related tests;
- bounded VERIFIED Knowledge and Decision inclusion;
- freshness/dirty-state warnings;
- retrieval ID and telemetry.

Test:

- known-location request does not waste retrieval;
- unknown-location request receives useful candidates;
- stale Map does not pretend to be current;
- embeddings unavailable falls back to structural retrieval;
- multiple active Work ambiguity is explicit;
- response remains bounded.

Exit criterion:

> In field tests, `project_enter` is at least as useful as current `project_status` plus the first manual discovery step.

Rollback: façade can return current status-only behavior.

---

### Phase 5 — Unified `project_lookup` and retrieval quality loop

**Goal:** make Project Intelligence win against broad native search often enough that agents choose it naturally.

Implement:

- structural + semantic + test/dependency expansion;
- Knowledge/Decision fusion;
- reranking with freshness/confidence;
- retrieval telemetry;
- implicit quality scoring from actual reviewed/changed paths;
- Dashboard/admin retrieval quality diagnostics;
- benchmark fixtures for representative projects.

Test:

- top-k recall;
- bad/stale alias correction;
- multilingual domain terms;
- exact identifier preservation;
- cross-layer flows (entrypoint -> service -> persistence -> tests);
- degraded embeddings;
- latency and payload budgets.

Exit criterion:

> Representative unknown-location tasks show a measurable reduction in broad discovery before the first relevant source inspection/edit.

Rollback: focused legacy search remains available internally.

---

### Phase 6 — Automatic Project Map learning and Knowledge candidates

**Goal:** remove routine reconciliation ceremony while improving future retrieval.

Implement:

- work-closure reconciliation planner;
- automatic structural refresh for affected paths;
- semantic Map update from validated bounded observations already produced by work;
- source-hash/provenance binding;
- retrieval-miss correction when actual work proves better locations;
- DRAFT Knowledge candidate pipeline from high-value work observations;
- review/batch policy for Knowledge candidates.

Requires ADR review for Knowledge publication semantics.

Test:

- no filler semantic entries;
- stale hash invalidation;
- current symbol/path validation;
- ordinary Work cannot produce VERIFIED Knowledge without review;
- completed Work with no reusable learning causes no extra model call;
- future lookup benefits from prior work.

Exit criterion:

> Project Map improves from normal engineering without requiring a separate routine model-facing reconciliation tool.

Rollback: candidates can be discarded; current reconciliation API retained.

---

### Phase 7 — Host-native observability adapters

**Goal:** make Dashboard truth depend less on model bookkeeping.

Implement per supported host, only where official capabilities exist:

- session lifecycle;
- subagent lifecycle;
- stable correlation;
- tool/check lifecycle when available;
- Work/AgentRun linking;
- terminal run state;
- safe repository-delta evidence.

Publish explicit coverage matrix.

Test black-box:

- start/stop;
- restart;
- subagent;
- tool/check;
- missing hook;
- unsupported host;
- unattributed external repository change.

Exit criterion:

> A missed optional agent progress call no longer makes active/completed work invisible when the host supplied authoritative lifecycle evidence.

Rollback: adapter-specific; control-plane-only mode remains valid.

---

### Phase 8 — Outcome-centric Dashboard projection

**Goal:** the human stops caring whether the implementation used Work, Task, or Epic.

Implement:

- root/child Work projection;
- assurance mode badge;
- plan progress;
- current human decision/blocker;
- review/findings/check summaries;
- Project Intelligence learning status;
- technical-detail drill-down;
- project portfolio and history based on outcome projection.

Preserve current entity debug/detail pages temporarily.

Test:

- no N+1 regression;
- read-only invariant;
- multi-project deterministic ordering;
- root Epic does not show duplicate backing Task Work;
- accessibility/responsive acceptance.

Exit criterion:

> A user can leave for a week, return to the Dashboard, and understand project state without knowing internal entity semantics.

Rollback: old read views remain available.

---

### Phase 9 — Collapse default MCP catalog and agent instructions

**Goal:** remove the rule mountain only after mechanics no longer require it.

Implement:

- default agent MCP server exposes façade only;
- legacy server is opt-in;
- installer/repair updates supported host registration;
- always-on bootstrap reduced to the small invariant contract;
- `ai-layer-workflow` skill repurposed for exceptional managed recovery/admin detail or removed from normal routing;
- old tool descriptions marked compatibility-only.

Test:

- supported host install/update/repair;
- weak-agent journey success;
- tool-choice confusion rate;
- static schema byte reduction;
- no loss of strict guarantees;
- legacy server compatibility.

Exit criterion:

> A fresh supported agent can complete ordinary and STANDARD journeys without being taught internal Work/Task/Epic mechanics.

Rollback: installer can switch back to legacy server registration.

---

### Phase 10 — Default switch, deprecation, field acceptance, release hardening

**Goal:** prove the new model on real projects before deleting compatibility.

Run:

- multi-project field trials;
- long-lived continuation after days/week;
- real Codex/Claude/Cursor acceptance;
- ordinary, reviewed, escalated, planned/Epic journeys;
- embeddings unavailable;
- database/service restart;
- dirty worktree;
- worker crash;
- partial host coverage;
- privacy audit;
- migration upgrade from supported versions;
- full `make preflight`.

Measure against Phase 0 baseline.

Only then:

- update canonical `PRODUCT_GOAL.md`, `ROADMAP.md`, `ARCHITECTURE.md`, current agent contract, and affected ADR status;
- make new façade the documented release path;
- start timed deprecation of legacy MCP;
- publish release only when committed artifacts/gates agree.

Exit criterion:

> Real field evidence shows lower agent ceremony/discovery cost and better human continuity without weaker correctness or observability.

---

## 18. Test matrix

Every phase that changes behavior must add focused tests capable of falsifying the new guarantee.

### Protocol

- start new work;
- resume current work;
- multiple active Work ambiguity;
- explicit reviewed assurance;
- explicit planned assurance;
- native -> reviewed promotion;
- reviewed -> planned promotion if supported;
- duplicate call;
- stale action token;
- invalid cross-project token;
- process restart.

### Task assurance

- independent actor requirement;
- mutation before worker binding rejected;
- read-only reviewer/discovery;
- findings -> FIX -> re-review;
- remediation cap;
- worker lease recovery;
- verification evidence;
- cancellation.

### Persistence

- fresh migration;
- supported upgrade;
- partial old linkage;
- Task with backing Work;
- Epic with Tasks;
- root/child Work hierarchy;
- concurrent Work creation;
- concurrent managed transition.

### Project Intelligence

- top-k retrieval;
- exact identifier;
- multilingual alias;
- related test;
- stale semantic row;
- embeddings unavailable;
- structural fallback;
- Knowledge stale/verified distinction;
- irrelevant Knowledge suppression.

### Learning

- no source bodies;
- semantic path/symbol validation;
- source-hash staleness;
- candidate provenance;
- no automatic VERIFIED Knowledge;
- no filler reconciliation.

### Observability

- host observed;
- agent reported;
- inferred unattributed;
- stale run;
- transport-only activity not called "working";
- no prompt/source/raw command leakage.

### Dashboard

- outcome grouping;
- Epic child progress;
- no duplicate Task Work cards;
- attention ordering;
- pagination;
- project scope preservation;
- read-only behavior.

### Installation

- new façade install;
- legacy opt-in;
- repair;
- upgrade;
- uninstall;
- target-repository zero-footprint.

---

## 19. Risk register

### Risk: façade becomes a new generic workflow engine

Mitigation:

- façade orchestrates existing Work/Task/Epic owners;
- no duplicate Task transition tables;
- no generic BPMN/state-machine framework;
- every action maps to current concrete product semantics.

### Risk: one `work_continue` schema becomes huge and ambiguous

Mitigation:

- use a discriminated, bounded report union;
- split only when real host/tool-choice tests show ambiguity;
- keep internal types separate even if transport is unified.

### Risk: automatic retrieval returns irrelevant context

Mitigation:

- strict result caps;
- confidence/freshness ranking;
- path-overlap signals;
- benchmark + implicit retrieval feedback;
- no requirement that the model consume every returned item.

### Risk: automatic learning pollutes Project Map/Knowledge

Mitigation:

- structural facts stay scanner-owned;
- semantic Map entries require current path/symbol validation + hash provenance;
- Knowledge remains DRAFT until review;
- corrections/removal supported;
- no completion requirement to invent learning.

### Risk: new Work hierarchy destabilizes existing Dashboard/history

Mitigation:

- additive schema;
- compatibility projection;
- backfill tests;
- no destructive removal before default switch stabilizes.

### Risk: host integrations are too inconsistent

Mitigation:

- capability matrix;
- per-host adapters;
- truthful partial coverage;
- façade works in MCP-only mode;
- no fabricated universal hook model.

### Risk: long-lived redesign branch diverges from `main`

Mitigation:

- integration branch receives only reviewed bounded slices;
- periodically merge/reconcile `main` deliberately between phases, never during an unrelated slice;
- run migration/architecture/preflight gates after each reconciliation;
- final PR to `main` only after field acceptance.

### Risk: trying to optimize exact tokens we cannot observe

Mitigation:

- distinguish configured/observed/host-hidden;
- use schema/payload bytes and tokenizer-independent estimates for relative comparisons;
- never claim provider billing savings without provider evidence.

---

## 20. Branch and PR strategy

### Integration branch

User-testable integration branch:

```text
redesign/agent-native-workflow
```

This branch is the stable place to test the redesign as it develops.

### Bounded implementation branches

Do not implement all phases directly in one giant unreviewable commit.

For each bounded slice:

```text
redesign/agent-native-workflow-p0-baseline
redesign/agent-native-workflow-p1-facade-contract
redesign/agent-native-workflow-p2-work-relations
...
```

or smaller task-specific variants when a phase is still too large.

Each slice:

1. branches from the current integration branch;
2. inspects current source/tests/contracts;
3. changes only that bounded capability;
4. runs focused checks;
5. performs independent self-review;
6. runs required repository gates;
7. opens a PR back to `redesign/agent-native-workflow`;
8. merges only after the slice is verified/reviewed;
9. stops before beginning the next slice.

The integration branch can be tested locally throughout the program.

### Final merge

Do not merge the integration branch to `main` until the new default path has passed field acceptance and the canonical docs/ADRs have been reconciled.

---

## 21. Local testing workflow for the integration branch

Once implementation starts:

```bash
git fetch origin
git switch redesign/agent-native-workflow
git pull --ff-only
make dev-setup
```

Use focused tests during a slice.

Before publishing a code/governance slice:

```bash
make fast-gate
make preflight
```

For manual product testing, install/run from the branch using the repository-supported development/runtime procedure for that phase; do not use an unrelated globally installed AI Layer as evidence for branch behavior.

The plan must be updated when a phase discovers a false assumption. Do not preserve an obsolete step merely because it was written here.

---

## 22. Program success metrics

The redesign succeeds only if both sides improve.

### Agent-side

- fewer model-visible tools in the default catalog;
- lower static schema bytes;
- fewer control-plane round trips per accepted result;
- lower duplicate/wrong workflow tool-call rate;
- lower broad-search calls before relevant source;
- higher Project Intelligence top-k hit rate;
- lower time/tool calls to first correct edit;
- successful continuation without chat reconstruction;
- weak-agent STANDARD journey succeeds without internal FSM manual.

### Human-side

- percentage of substantive outcomes with durable terminal state;
- stale/invisible Work rate;
- time to answer "what happened in this project?";
- percentage of active work with truthful actor/coverage;
- duplicate/fragmented outcome cards;
- cross-project attention accuracy;
- ability to resume a week-old outcome from Dashboard/state alone.

### Quality-side

- managed review guarantees unchanged or stronger;
- no privacy regression;
- no source-truth regression;
- no migration/concurrency regression;
- no target-repository footprint regression;
- no increase in unresolved Project Intelligence stale/incorrect hints.

---

## 23. Definition of Done for the redesign program

The program is complete only when all of the following are true on supported hosts:

1. A normal substantive request can be executed with `project_enter -> native work -> work_finish`, plus optional `project_lookup`.
2. An explicit STANDARD request creates one user-visible Work outcome and completes IMPLEMENT/REVIEW/FIX semantics without exposing Task FSM procedure to the parent model.
3. Native work can escalate into reviewed assurance without changing its human Work identity or losing pre-managed provenance.
4. A large outcome can promote to a root Work + Epic + child Work plan without duplicate backing Work clutter.
5. `project_enter`/`project_lookup` measurably reduce discovery on representative unknown-location tasks.
6. Useful Project Map learning occurs from real work without a mandatory separate reconciliation call.
7. VERIFIED Knowledge remains review-gated while useful candidates can be captured naturally.
8. Supported host observability keeps Dashboard useful even when the model omits optional progress bookkeeping.
9. Dashboard presents project outcomes first and internal Work/Task/Epic mechanics only as technical detail.
10. Default agent MCP exposes the small façade; legacy broad catalog is opt-in.
11. Always-on agent instructions contain only entry/source/evidence invariants, not a state-machine manual.
12. Restart, duplicate delivery, stale tokens, dirty trees, worker crashes, embedding failure, and partial host coverage behave safely.
13. Migration from supported existing installations is verified on real PostgreSQL.
14. Privacy and zero-footprint contracts remain intact.
15. `make preflight` passes on the exact final worktree and supported-host black-box acceptance is recorded.

---

## 24. First implementation slice after this plan is accepted

The next bounded task should be **Phase 0 only**:

> Build the executable baseline/journey measurement harness and produce the first current-state report. Do not introduce the new façade or modify workflow semantics in that same slice.

Why first:

- it provides the baseline needed to prove later improvements;
- it catches hidden schema/payload costs;
- it gives reproducible examples of the "agent ignores the intended workflow" problem;
- it prevents another redesign from being judged only by how elegant its code looks.

After Phase 0 is completed and independently reviewed, stop. The following user-approved pass should review Phase 0 as a skeptical reviewer before Phase 1 begins.
