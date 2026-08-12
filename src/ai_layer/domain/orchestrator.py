from __future__ import annotations

from typing import Any

from ai_layer.domain.static_policy import static_policy_markdown

CRITICAL_ORCHESTRATOR_CONTRACT_VERSION = 4


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
        "epic_rule": "Existing Epic: epic_next owns lifecycle; task_next owns only its linked Task.",
    }


def critical_orchestrator_markdown() -> str:
    """Small always-on role boundary. Detailed procedure is returned dynamically by task_next/epic_next."""
    return """## AI Layer orchestrator
- Top-level coordinates; no external mutation; never edit repository files unless `task_next` grants `inline_micro_implement`.
- IMPLEMENT/FIX -> bound writable worker; DISCOVERY/REVIEW -> bound read-only worker. Record its result.
- Worker/tool unavailable -> block; no fallback. Active Epic -> `epic_next`; otherwise `task_next`.
"""


def native_bootstrap_markdown() -> str:
    """Single compact static kernel; runtime navigators own detailed procedure."""
    control_plane = """## AI Layer control plane
For registered projects:
- First project tool: `memory_context(task=<actual task>, project_root=<root>)`. Before it: no repo read/search, shell/SSH, edits, agents; no `task_current` or simple/read-only bypass.
- Follow navigator action; navigate again after transitions/worker returns.
- MICRO: obvious local low-risk only; never high-impact below/external mutation; uncertain -> STANDARD.
- Keep canonical root; one task/stage/worker. dirty worktree is a valid baseline; never stash/reset/restore/commit user work.
- Native skills choose relevance; `skill_get` on demand. AI Layer/delegation failure -> block; never bypass.
"""
    return critical_orchestrator_markdown() + "\n" + control_plane + "\n" + static_policy_markdown()


def mcp_bootstrap_instructions() -> str:
    """Tiny fallback when native bootstrap delivery is unavailable or drifted."""
    return (
        "For registered-project work, `memory_context` MUST be the first project-related tool call; before it, "
        "do not read/search/grep, run shell/SSH, edit, or start a subagent. Then use `epic_next` for an active "
        "Epic, otherwise `task_next`, and follow only its action. After every Task/Epic transition or worker "
        "return, navigate again before more project work. The top-level chat coordinates only except when "
        "task_next authorizes inline_micro_implement. If AI Layer/delegation fails, report/block instead of bypassing it."
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
