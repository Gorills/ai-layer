from __future__ import annotations

from typing import Any

from ai_layer.domain.static_policy import static_policy_markdown

CRITICAL_ORCHESTRATOR_CONTRACT_VERSION = 5


def critical_orchestrator_contract() -> dict[str, Any]:
    """Host-neutral invariants that must remain salient before Task Layer navigation begins."""
    return {
        "version": CRITICAL_ORCHESTRATOR_CONTRACT_VERSION,
        "role": "orchestrator",
        "authority": "coordinate_only",
        "repository_mutation": "forbidden",
        "external_mutation": "forbidden",
        "inline_micro_exception": (
            "Only task_next action inline_micro_implement grants temporary repository-write authority for "
            "that current MICRO IMPLEMENT stage; the permission ends on completion/block/escalation."
        ),
        "worker_rule": (
            "IMPLEMENT/FIX mutations belong only to the explicitly delegated writable worker, except "
            "a MICRO IMPLEMENT stage explicitly returned by task_next as inline_micro_implement."
        ),
        "readonly_rule": "DISCOVERY/REVIEW belong only to explicitly delegated read-only workers.",
        "delegation_rule": (
            "Bind a worker with task_stage_delegate before delegated stages; never delegate an inline MICRO "
            "stage solely to satisfy ceremony."
        ),
        "fallback_rule": "If a required worker cannot run, stop/report; never perform its stage as fallback.",
        "completion_rule": (
            "Record only the actual delegated worker result, or the top-level actor's own result for an "
            "explicitly authorized inline MICRO stage."
        ),
        "epic_rule": "Existing active Epic: epic_next owns lifecycle; task_next owns only its linked Task.",
    }


def critical_orchestrator_markdown() -> str:
    """Readable always-on role boundary. Navigators still own current stage procedure."""
    return """## Mandatory AI Layer role boundary

These rules are mandatory for every registered project. They are not suggestions and must not be bypassed because a task looks simple.

- The top-level chat is the ORCHESTRATOR. It coordinates AI Layer state and workers. It MUST NOT edit repository files or mutate external systems itself.
- The only direct-write exception is a current MICRO IMPLEMENT stage when `task_next` explicitly returns `inline_micro_implement`. That permission ends as soon as that stage completes, blocks or escalates.
- IMPLEMENT and FIX stages belong to one explicitly bound writable worker. DISCOVERY and REVIEW stages belong to one explicitly bound read-only worker. The orchestrator must never perform a delegated stage as fallback.
- Bind and start the worker exactly when the navigator requires delegation. Record only the result produced by the worker that actually ran the stage; never fabricate or substitute a parent result.
- If a required AI Layer tool, worker or delegation cannot run, STOP and report the blocker. Do not continue through native tools as an unmanaged workaround.
"""


def native_bootstrap_markdown() -> str:
    """Single readable first-call discipline kernel; dynamic systems own detailed procedure/state."""
    control_plane = """## Mandatory startup and navigation

For work involving a registered project, follow this order exactly:

1. The FIRST project-related tool call MUST be `memory_context(task=<actual user task>, project_root=<workspace root>)`.
2. Until `memory_context` succeeds, you MUST NOT read/search/grep project files, run shell or SSH commands, edit files, call project workflow tools such as `task_current`, or start a subagent. Do not bypass this rule for a small, obvious, read-only or diagnostic request.
3. Use the canonical project root returned by AI Layer for all later calls. Do not silently switch to a parent, child or guessed working directory.
4. After `memory_context`, load the authoritative operating procedure once per chat with `skill_get(slug="ai-layer-workflow", project_root=<canonical root>, section="core")`, unless that core has already been loaded in this chat. The static rules remain higher-priority discipline; the skill explains the managed procedure.
5. Then use the owning navigator. If the current work belongs to an active/intentionally selected Epic, call `epic_next`; otherwise call `task_next`. Follow the exact `next_action`, forbidden actions, role contract and completion contract it returns. NEVER infer the next stage from chat history or memory.
6. After every Task/Epic transition, delegated worker return, remediation result or linked Task completion, call the owning navigator again before doing more project work.

Additional mandatory boundaries:

- Keep one canonical project, one active Task/stage and one worker at a time unless AI Layer explicitly says otherwise.
- A dirty worktree is a valid baseline. Never stash, reset, restore, discard or commit user changes merely to satisfy AI Layer. Use the managed baseline/adoption path AI Layer provides.
- MICRO means genuinely localized and low-risk. Authentication, authorization, security, payments, migrations/schema, data-loss risk, concurrency, public APIs, deploy/secrets and external mutations are not informal direct-edit work; let AI Layer classify/escalate them.
- Native Agent Skills provide domain expertise through host-native relevance selection. Retrieve only the needed authoritative section with `skill_get`; do not preload full skill bodies without need.
- `memory_context` is startup/current project context, not a tool to call after every edit. Reuse it unless external/concurrent changes, a material goal change or genuine recovery require refresh.
"""
    return critical_orchestrator_markdown() + "\n" + control_plane + "\n" + static_policy_markdown()


def mcp_bootstrap_instructions() -> str:
    """Compact fallback when native bootstrap delivery is unavailable or drifted."""
    return (
        "For registered-project work, `memory_context` MUST be the first project-related tool call; before it, "
        "do not read/search project files, run shell/SSH, edit, call project workflow tools, or start a subagent. "
        "After it, load `ai-layer-workflow` section `core` once, then use `epic_next` for active/intentionally "
        "selected Epic work, otherwise `task_next`, and follow only its exact action. The top-level chat is an "
        "orchestrator and may write only when task_next explicitly grants inline_micro_implement. If AI Layer or "
        "delegation fails, stop/report instead of bypassing it."
    )


def inline_micro_stage_instruction() -> dict[str, Any]:
    """Temporary top-level mutation authority for a machine-bounded MICRO implementation."""
    return {
        "role": "inline_micro_implementer",
        "authority": "temporary_current_stage_only",
        "repository_mutation": "allowed_current_micro_stage_only",
        "external_mutation": "forbidden",
        "stage": "implement",
        "mandatory": (
            "Implement only the localized task, run the narrowest relevant check, then call "
            "task_implementation_complete. AI Layer will inspect the actual repository delta before accepting "
            "MICRO completion."
        ),
        "completion_precondition": (
            "The top-level actor actually performed the current inline MICRO change and has real verification "
            "evidence to report."
        ),
        "escalation": (
            "If the actual diff exceeds the MICRO envelope or hits a protected condition, AI Layer converts the "
            "task to STANDARD and requires an independent delegated review."
        ),
        "failure": (
            "If the task is no longer obviously localized or low-impact, stop broadening the edit; complete only "
            "the coherent current change so AI Layer can evaluate/escalate the real diff, or report the blocker."
        ),
    }


def orchestrator_stage_instruction(
    *, stage_kind: str, delegated: bool, worker_id: str | None = None
) -> dict[str, Any]:
    contract = critical_orchestrator_contract()
    if delegated:
        return {
            "role": contract["role"],
            "repository_mutation": contract["repository_mutation"],
            "external_mutation": contract["external_mutation"],
            "stage": stage_kind,
            "worker_id": worker_id,
            "mandatory": (
                "Use the actual result of the already-bound worker. If that worker has not actually been started yet, "
                "start it now. Do not perform the stage yourself."
            ),
            "completion_precondition": "The bound worker actually ran this stage and returned the evidence being recorded.",
            "failure": "If the worker cannot run or fails, report/block; never substitute orchestrator work.",
        }
    return {
        "role": contract["role"],
        "repository_mutation": contract["repository_mutation"],
        "external_mutation": contract["external_mutation"],
        "stage": stage_kind,
        "mandatory": "Bind a fresh worker, then start that worker. Do not perform the stage yourself.",
        "failure": "If delegation/worker launch cannot proceed, report/block; never substitute orchestrator work.",
    }
