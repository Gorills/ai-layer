# ADR 0026 — Agent-facing façade contract prototype

## Status

Accepted for the agent-native redesign prototype. This ADR freezes a future public boundary only.
ADR 0025 and the current broad `ai-layer-mcp` catalogue remain the operative runtime contract until
a later phase passes supported-host field acceptance and explicitly changes the default.

## Context

The current runtime correctly separates host-native engineering from Project Intelligence and from
the optional managed Task/Epic engines, but an agent that enters reviewed work still sees the
internal control-plane vocabulary directly: ordinary Work tools, `task_next`/stage delegation and
`epic_next` are separate navigation surfaces. That is truthful for the current implementation, but
it makes weak agents mirror backend mechanics and makes continuation more expensive than the
product model requires.

The redesign plan requires a small public façade that can express six target journeys without
exposing Task/Epic finite-state-machine mechanics:

1. short ordinary work;
2. longer ordinary work with optional review escalation;
3. explicitly reviewed/STANDARD work;
4. continuation after restart;
5. Epic-attached continuation;
6. escalation from native work into managed assurance.

Phase 1 must freeze that boundary before persistence or transition ownership changes. It must not
replace the current MCP implementation, installer defaults, Task engine, Epic engine, Work
persistence, or release artifact.

## Decision

### Work remains the universal execution anchor

One substantive user-visible request is anchored by one durable WorkItem. Ordinary host-native work,
managed Task assurance and Epic planning may all refer to the same Work identity.

A managed Task remains an optional assurance workflow attached to Work. It does not replace Work
and it does not become mandatory for ordinary repository actions.

An Epic remains a planning/integration artifact. Epic orchestration may select or attach Work and
managed assurance, but agent-facing continuation does not require the caller to navigate a second
public FSM.

The current project-global one-open-managed-Task invariant is preserved. This ADR does not claim
per-Work concurrent managed Tasks that current PostgreSQL constraints do not support.

### Future public façade

The prototype freezes exactly four candidate agent-facing operations:

- `project_enter` — start or resume durable project work and return one public next action;
- `project_lookup` — retrieve bounded Project Intelligence breadcrumbs only when location/context is
  needed;
- `work_continue` — report completion of the current public action and request the next public
  action;
- `work_finish` — record the durable terminal Work outcome after the server says managed/native
  execution is ready to finish.

The public `next_action.kind` vocabulary is exactly:

- `native_engineering`;
- `run_worker`;
- `human_decision`;
- `done`.

Task stage names, Task navigation tools, Epic navigation tools and worker-lease mechanics are not
part of the public façade DTO.

`run_worker` may carry a coarse public worker kind (`change`, `independent_check`, `correction`) so
the host knows what kind of isolated worker to run. This is an execution instruction, not a public
copy of TaskStage state.

### Server owns transitions

The façade does not implement a new workflow engine. The prototype accepts an abstract internal
directive and maps it to one of the four public actions. In the eventual runtime implementation,
existing Work/Task/Epic application services remain authoritative for persistence, stage
eligibility, findings, verification, leases, remediation and Epic scheduling. The façade will
translate their authoritative state into a public action; clients will not reconstruct transitions.

A `done` action means no further engineering/review action is required. Before durable Work closure
it carries a terminal action token accepted by `work_finish`. A successful `work_finish` response
may return `done` with no further token.

### Opaque action token and state version

Every actionable response carries:

- an opaque `action_token`;
- the observed `state_version`;
- the public action kind.

The token is server-owned and binds at least project identity, Work identity when one is selected,
state version and public action kind. The token must not encode those values in readable form.
Production tokens must be generated with unguessable server-held entropy/key material.

Phase 1 uses an HMAC-backed deterministic token issuer only to make the contract executable and
testable. It is not registered in product runtime and is not a production credential scheme.

Submission semantics are:

- current token, first valid report -> advance;
- already-consumed token + identical canonical report -> idempotent replay;
- already-consumed token + different report -> idempotency conflict;
- well-formed non-current, non-consumed token -> stale action;
- malformed token -> invalid action token.

On stale action the eventual transport should tell the caller to re-enter with
`project_enter(intent="resume")` rather than guessing the new internal state.

When multiple active WorkItems make resume ambiguous, `project_enter` returns
`human_decision`; it does not silently select one.

### Clean and dirty promotion are distinct

Escalating existing ordinary Work to managed assurance must preserve repository truth.

- **clean promotion** — attach/create managed assurance from the current clean Work baseline;
- **dirty promotion** — adopt the existing dirty repository state as the managed baseline at the
  promotion point.

Dirty promotion must not reset, rebase, stash, discard or retrospectively attribute pre-promotion
edits to a new managed worker. Existing Task adoption/provenance rules remain authoritative when
this design is implemented.

The clean/dirty strategy is an internal contract and is not emitted as normal public façade state.

### Project Intelligence remains source-navigation support

`project_lookup` is optional. It returns bounded Project Map/Knowledge/Decision breadcrumbs, not
source bodies and not a replacement for current repository inspection. Current source remains
authoritative before edits or code-truth claims.

### Context budgets are protocol contracts

The prototype names explicit context budgets because reducing agent-facing control-plane surface is
the concrete Phase 1 objective:

- aggregate four-tool definition catalogue: at most 7 KiB serialized JSON;
- ordinary enter/lookup response: at most 8 KiB;
- action/finish response: at most 4 KiB.

The committed Phase 0 baseline is the comparison authority. Contract tests require the prototype
catalogue to be at least 90% smaller than the measured current runtime catalogue, while retaining
input and output schemas.

These budgets apply only to this façade contract. They do not change existing runtime limits.

### Compatibility and rollout

Phase 1 is additive design evidence only:

- current `ai-layer-mcp` remains registered and unfiltered;
- none of the four façade tool names are registered in `TOOL_HANDLERS`;
- installer/bootstrap defaults do not change;
- ADR 0025 envelopes remain authoritative for the current runtime;
- no legacy tool is removed;
- no persistence schema or migration changes.

The executable prototype lives under repository `scripts/`, with golden fixtures and tests. It is
deliberately outside `src/ai_layer`, so the committed application wheel and current product behavior
remain unchanged.

A later phase may implement this boundary in product source only after its required persistence and
server-owned transition changes exist. Default switching/removal is later still and requires
supported-host acceptance.

## Consequences

- The future agent contract has one obvious entry/resume tool and one action-continuation tool.
- Work identity can survive native-to-reviewed escalation and Epic attachment without exposing
  internal FSM navigation.
- Weak-model simulations can test schema/tool disambiguation before runtime behavior changes.
- Stale/retry semantics are frozen before persistence implementation.
- Phase 1 does not prove real host usefulness, latency or tool-selection behavior; those remain field
  evidence for later phases.
- The current runtime has no behavioral change from this ADR/prototype.

## Verification and exit criterion

Phase 1 is complete when executable tests prove:

- exactly four public façade tools and four public actions;
- tool input shapes are disjoint for representative weak-model calls;
- all six target journeys are expressible using only those tools/actions;
- multiple active Work, existing managed assurance, unrelated new work, Epic continuation and dirty
  escalation have explicit non-destructive behavior;
- opaque token shape, state binding, stale-token handling and idempotent replay/conflict semantics;
- golden input/output schema fixture stability;
- measured context budgets and at least 90% catalogue reduction from committed Phase 0 evidence;
- none of the candidate façade tools are registered in the current MCP runtime;
- the existing repository regression, PostgreSQL and browser gates remain green.

## Rollback

Delete/disable the prototype ADR, script, fixture and tests. Because Phase 1 does not register the
façade, change product source, modify persistence or change installer defaults, rollback requires no
runtime migration or compatibility action.
