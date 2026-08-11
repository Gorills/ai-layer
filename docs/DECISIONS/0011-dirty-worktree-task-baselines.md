# ADR 0011 — Managed tasks may start from dirty worktree baselines

## Status

Accepted for v0.11.1.

## Context

The previous Task Layer rejected a new managed task when Git already contained unknown staged, unstaged, or untracked work. This made a clean worktree an implementation precondition even though the Task Layer already persists immutable repository snapshots and computes repository deltas from those snapshots. In practice coding agents worked around the restriction with `git stash`, creating unnecessary risk to user-owned work and coupling AI Layer task boundaries to Git commit/stash hygiene.

## Decision

`task_create` accepts a dirty worktree. At task creation AI Layer captures the exact repository state as the immutable task baseline and separately records the pre-existing Git-visible changed paths as provenance metadata. Managed file delta is always computed from the captured baseline, not from Git `HEAD`.

`task_adopt` keeps its narrower meaning: use it when the already-existing dirty changes are themselves the implementation being brought under review, so AI Layer must not claim a managed implementation stage for them.

AI Layer policy forbids an agent from using stash/reset/restore/commit merely to make a repository clean enough for Task Layer. Such Git operations remain possible when explicitly required by the user's actual task.

The sequential invariant remains unchanged: one open mutating task and one active stage per project. Repository drift before delegation and drift after a blocked boundary are still rejected. Actor identity during a delegated write stage remains protocol-level rather than cryptographically proven.

For MICRO completion, if the managed task modifies a path that was already dirty at task creation, the task escalates to STANDARD review because Git `HEAD` cannot provide an exact line-count delta relative to that dirty baseline without storing repository contents.

## Consequences

- Multiple reviewed AI Layer tasks may accumulate before one Git commit.
- Pre-existing unrelated user changes no longer block task creation.
- `final_changes` remains task-specific because it is computed from task baseline to terminal state.
- The Task view/delegation contract exposes `preexisting_changes` so agents know those edits must be preserved.
- No repository source contents are added to durable snapshot storage; snapshots remain path/hash/stat metadata only.
