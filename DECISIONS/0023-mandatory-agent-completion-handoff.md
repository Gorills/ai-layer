# ADR 0023 — Mandatory agent completion handoff

## Status

Accepted for repository development.

## Context

Repository work often spans multiple chats. A technically correct completion message can still leave the human to reconstruct the next priority and rewrite context for a fresh agent. Chat history is not durable source truth, but a concise handoff can make continuation cheaper when it clearly directs the next agent back to current source, Git state and executable verification.

## Decision

Every final response after completed repository work must contain two explicit user-visible sections:

1. **What next** states the next concrete recommended action, or explicitly says that no required work remains.
2. **Prompt for the next chat** supplies a ready-to-copy, self-contained prompt for a fresh agent. It names the intended outcome, relevant current context and constraints, known verification evidence, and requires inspection of current source and Git state before making code-truth claims or edits.

The handoff must remain truthful. It may not imply that a commit, push, publication, deployment or review occurred when it did not. When no required follow-up exists, the response still provides an optional audit, publication or next-objective prompt rather than inventing incomplete work.

## Consequences

- The human always knows the recommended continuation without having to ask again.
- A new chat receives a usable starting prompt while current repository evidence remains authoritative.
- Completion messages become slightly longer, but the required structure is bounded and directly supports cross-chat continuity.
