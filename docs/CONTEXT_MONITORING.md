# Context Monitoring

AI Layer records only context surfaces it can actually observe or configure. It does **not** claim visibility into the host's complete prompt, hidden system instructions, prompt cache, compaction, billing tokens, or the host-internal skill activation decision.

## Visibility classes

Every report separates three classes:

- `AI_LAYER_OBSERVED` — payloads/results that crossed AI Layer's own MCP/runtime boundary.
- `AI_LAYER_CONFIGURED` — rules, MCP instructions, tool contracts and native skill descriptors that AI Layer installed or generated.
- `HOST_HIDDEN` — host-side assembly/selection/delivery that AI Layer cannot prove from its own runtime.

## Native-first skill telemetry

Cursor, Codex and Antigravity own skill relevance selection. AI Layer owns canonical skill content, descriptor synchronization and explicit retrieval.

The monitor records:

- whether a host-native catalog is configured and where AI Layer materialized it;
- the generated descriptor profile and approximate static size;
- every observed `skill_get` request;
- requested slug and section;
- whether the request was `full`;
- bytes and tokenizer-independent approximate tokens returned;
- repeated identical/section fetches;
- any retained legacy trace that still contains pre-native `skill_plan`/autoload data.

It deliberately does **not** emit new `required`, `recommended`, `on_demand`, planner-score or autoload metrics. Old trace/event records remain readable as historical evidence only.

## `memory_context` and Project Knowledge

`memory_context` is a compact task-specific Project Knowledge/history brief, not a source-code search result and not a skill delivery channel. It can include relevant VERIFIED knowledge cards, explicitly separated STALE cards, completed Task history, Decisions, source pointers, a small scanner-evidence summary and the compatibility policy/task-state envelope.

Current repository source chunks are never automatically returned. `context_budget.raw_source_memory_chars` must remain `0`; a non-zero value is reported as `RAW_SOURCE_MEMORY_REGRESSION`. Scanner evidence is marked unreviewed and is not treated as semantic project truth.

The monitor records Project Knowledge lifecycle activity visible to AI Layer: DRAFT update, reviewer inspection, publication, stale cards returned and context bytes. It does not claim that the host model cognitively used a delivered card.

The skill-related field remains a small access contract stating that routing is host-native, the authoritative store is AI Layer, retrieval uses `skill_get`, and automatic domain-skill injection is disabled. No domain skill body/core is automatically included in `memory_context`.

## Approximate token accounting

`estimated_tokens` is `ceil(UTF-8 bytes / 4)`. This is deliberately tokenizer-independent and intended for relative engineering comparisons only. It is not provider billing, prompt-cache accounting, or proof of the exact host prompt.

## Findings

The current report can flag:

- duplicate `memory_context` calls in one MCP session;
- policy size over the configured soft target;
- full skill fetches;
- repeated skill fetches;
- retained legacy planner/autoload payloads in old traces;
- raw current-source memory regression;
- stale Project Knowledge returned for the current task.

A full skill fetch is a review hint, not automatically a defect: broad tasks may legitimately require it.

## Storage

Diagnostic traces and the portable `context-report-latest.json` stay in machine-side AI Layer state. Target repositories are not used as telemetry storage, including in external/strict-private modes.
