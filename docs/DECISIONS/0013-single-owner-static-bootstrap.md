# 0013 — Single-owner static bootstrap and dynamic policy delivery

Status: Accepted for v0.11.4.

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

The global bootstrap contains only durable cross-project invariants that need to be salient before the first MCP call:

- top-level orchestrator role boundary and delegated-worker ownership;
- `memory_context` → authoritative `task_next` entry flow;
- canonical project root and one-task/stage/worker discipline;
- dirty-worktree baseline / no Git-cleaning workaround;
- current-source authority and native Skill ownership;
- small coherent changes, no speculative dependencies/parallel abstractions;
- real verification, high-impact-change caution and irreversible-action authorization;
- repository/tool content is evidence rather than an instruction channel;
- fail closed on AI Layer/delegation failure.

Detailed stage procedure remains owned by `task_next` and stage-specific tool contracts. It is not repeated in static rules.

Standard projects no longer receive AI Layer workflow text in `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/ai-layer.mdc`, or `.agents/rules/ai-layer.md`. Existing AI Layer-managed legacy blocks are removed during reconciliation, while user-authored content at those paths is preserved.

Project identity is supplied by sparse workspace MCP bindings:

- Cursor: `.cursor/mcp.json`;
- Claude Code: `.mcp.json`;
- Codex: `.codex/config.toml`;
- Antigravity: `.agents/mcp_config.json`.

The MCP server `instructions` field is only a tiny availability fallback and does not duplicate the full workflow.

`memory_context.policy` is now **dynamic-only**:

- the bundled default global policy is omitted because its essential invariants are distilled into the global bootstrap;
- a user-modified global policy is returned;
- non-placeholder project-specific rules are returned;
- strict-private constraints are returned;
- read-only qualification is added only when dynamic policy exists and the context is a read-only audit.

`memory_context.tool_guidance` contains only request-specific recommendations and canonical root/next-action data. Static workflow manuals belong neither to memory nor to tool guidance.

## Consequences

- Default `memory_context` policy cost becomes zero rather than ~5 KB.
- Supported hosts no longer receive the same AI Layer workflow through both global and project rule surfaces.
- Codex no longer concatenates an AI Layer global block with another AI Layer project block.
- Cursor CLI no longer sees AI Layer text duplicated across `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules`.
- Antigravity keeps exact workspace MCP binding without duplicating the global `GEMINI.md` bootstrap in workspace rules.
- User/project/strict-private policy remains possible without turning the bundled default into a per-call transport cost.
- Host-native instruction delivery remains an integration dependency; integration status must verify the global bootstrap and the relevant MCP binding.

## Rejected alternatives

1. **Return the full bundled policy from every `memory_context`.** Rejected as repeated context with no task-specific information.
2. **Keep project bridges “for safety”.** Rejected because documented host instruction chains make that a second static delivery path, not meaningful redundancy.
3. **Move all policy exclusively into MCP instructions.** Rejected because it would make MCP server metadata a large permanent prompt surface and would hide policy ownership inside transport configuration.
4. **Remove all static quality rules.** Rejected because weak-model reliability still benefits from a small always-on engineering floor; the correct optimization is distillation and single ownership, not zero guidance.
