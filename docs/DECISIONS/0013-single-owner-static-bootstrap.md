# 0013 — Single-owner static bootstrap and dynamic policy delivery

Status: Accepted for v0.11.4; clarified 2026-08-12.

## Context

By v0.11.3 AI Layer had removed eager Skill content and raw-source memory, but the same workflow/policy was still repeated across several prompt surfaces:

- global native host bootstrap;
- repository `AGENTS.md` / `CLAUDE.md` / Cursor and Antigravity project rules;
- MCP server instructions;
- the `policy` and static `tool_guidance` fields returned by every `memory_context` call.

This repetition is not neutral. Cursor documents that applied Rules are inserted at the start of model context, and Cursor CLI also reads root `AGENTS.md` and `CLAUDE.md`. Codex documents a merged instruction chain containing global `~/.codex/AGENTS.md` plus project `AGENTS.md`. Antigravity documents global `~/.gemini/GEMINI.md` rules plus workspace rules, and separately supports workspace MCP binding in `.agents/mcp_config.json`.

Official references used for this decision:

- https://docs.cursor.com/context/rules-for-ai
- https://docs.cursor.com/en/cli/using
- https://developers.openai.com/codex/guides/agents-md
- https://antigravity.google/docs/ide-rules
- https://antigravity.google/docs/mcp

## Decision

Static AI Layer behavior has exactly one authoritative prompt owner per supported host: the **global native bootstrap**.

The global bootstrap is a **Discipline Kernel**. It contains the durable cross-project rules that must be understood before and during the first managed interaction:

- `memory_context` is the mandatory first project-related tool call and repository/shell/edit/subagent work is forbidden before it succeeds;
- the canonical project root returned by AI Layer must be reused;
- the top-level chat is an orchestrator, not the normal implementation/review worker;
- delegated IMPLEMENT/FIX work belongs to one bound writable worker; DISCOVERY/REVIEW belongs to one bound read-only worker;
- direct top-level repository mutation exists only for an explicit `inline_micro_implement` action;
- `task_next`/`epic_next` own current workflow state and the next action; chat history must not be used to infer a stage;
- dirty worktrees are valid baselines and must not be destructively cleaned to satisfy AI Layer;
- current source, real evidence, verification, high-impact caution, irreversible-operation authorization and conservative engineering rules remain mandatory;
- token economy remains mandatory, including concise final-response limits, but instructions must remain explicit enough for weak models to understand them;
- AI Layer/delegation failure is fail-closed rather than permission to bypass the system.

The bootstrap deliberately does **not** contain the full Task/Epic procedure or domain expertise. After `memory_context`, it requires the authoritative bundled `ai-layer-workflow` Skill `core` to be loaded once per managed chat. That Skill explains the stable operating procedure, including Task/Epic lifecycle, delegation, MICRO, adoption, dirty worktrees, recovery and selective Skill loading. Additional workflow sections are retrieved only when needed.

The three owners therefore have distinct responsibilities:

1. **Static Discipline Kernel** — mandatory preconditions, role boundaries and engineering invariants that must already be understood on the first model call.
2. **`ai-layer-workflow` Skill** — current versioned procedure/manual, delivered through progressive disclosure after startup.
3. **`task_next` / `epic_next` and stage-specific tool contracts** — live durable state and the exact current next action. These always take precedence over lifecycle examples in the Skill.

There is no product requirement to minimize the Discipline Kernel to a particular historical byte count. Its budget is a comprehension budget: keep it focused and reasonably small, but never replace clear mandatory instructions with telegraphic abbreviations merely to save a few hundred tokens. Context economy comes primarily from keeping detailed procedure, current state and domain knowledge progressive.

Standard projects no longer receive AI Layer workflow text in `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/ai-layer.mdc`, or `.agents/rules/ai-layer.md`. Existing AI Layer-managed legacy blocks are removed during reconciliation, while user-authored content at those paths is preserved.

Project identity is supplied by sparse workspace MCP bindings:

- Cursor: `.cursor/mcp.json`;
- Claude Code: `.mcp.json`;
- Codex: `.codex/config.toml`;
- Antigravity: `.agents/mcp_config.json`.

The MCP server `instructions` field is only a compact availability fallback and does not duplicate the full workflow.

`memory_context.policy` is **dynamic-only**:

- the bundled default global engineering policy is omitted because the same durable invariants are rendered by the global Discipline Kernel;
- a user-modified global policy is returned;
- non-placeholder project-specific rules are returned;
- strict-private constraints are returned;
- read-only qualification is added only when dynamic policy exists and the context is a read-only audit.

`memory_context.tool_guidance` contains only request-specific recommendations and canonical root/next-action data. Static discipline and workflow manuals belong neither to memory nor to tool guidance.

## Consequences

- Default `memory_context` policy cost remains zero rather than repeatedly transporting bundled global policy.
- Weak models receive explicit, categorical startup and role rules instead of byte-optimized shorthand.
- The stable workflow manual can evolve with AI Layer without increasing every first model call by the size of the whole procedure.
- Supported hosts no longer receive the same AI Layer workflow through both global and project rule surfaces.
- Codex no longer concatenates an AI Layer global block with another AI Layer project block.
- Cursor CLI no longer sees AI Layer text duplicated across `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules`.
- Antigravity keeps exact workspace MCP binding without duplicating the global `GEMINI.md` bootstrap in workspace rules.
- User/project/strict-private policy remains possible without turning the bundled default into a per-call transport cost.
- Host-native instruction and Skill delivery remain integration dependencies; integration status must verify the global bootstrap, native Skill publication and relevant MCP binding.

## Rejected alternatives

1. **Return the full bundled policy from every `memory_context`.** Rejected as repeated context with no task-specific information.
2. **Keep project bridges “for safety”.** Rejected because documented host instruction chains make that a second static delivery path, not meaningful redundancy.
3. **Move all policy exclusively into MCP instructions.** Rejected because it would make MCP server metadata a large permanent prompt surface and hide policy ownership inside transport configuration.
4. **Remove all static quality rules.** Rejected because weak-model reliability benefits from an always-on engineering floor; the correct optimization is single ownership and progressive procedure, not zero guidance.
5. **Compress the bootstrap to a fixed byte target.** Rejected because a byte-golf constraint can preserve keywords while degrading weak-model comprehension. The upper bound protects against accidental growth; semantic/readability tests protect the actual contract.
6. **Put the complete Task/Epic manual in the bootstrap.** Rejected because procedure is large, versioned and only partly relevant to any given step. The bundled workflow Skill plus authoritative navigators provide progressive disclosure without losing discipline.
