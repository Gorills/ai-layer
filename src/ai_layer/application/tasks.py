from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_layer.application.managed_work import sync_task_backing_work
from ai_layer.core.paths import project_state_path
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.domain.agent_contract import (
    ENVELOPE_MANAGED_NEXT,
    with_envelope,
)
from ai_layer.domain.orchestrator import orchestrator_stage_instruction
from ai_layer.tasks.delegation_contract import worker_job_packet
from ai_layer.tasks.service import (
    adopt_task,
    cancel_task,
    cleanup_current_review_sandbox,
    complete_current_stage,
    complete_stage,
    create_task,
    current_task,
    delegate_current_stage,
    next_task_action,
    prepare_current_review_sandbox,
    recover_disconnected_worker,
    resume_task,
    run_current_review_check,
)
from ai_layer.tasks.state_store import read_json
from ai_layer.tasks.worker_leases import heartbeat_worker, reap_stale_worker_leases


def _project(db, project_root: str | Path):
    return get_project(db, project_root)


def _with_task_work(db, project, result: dict, *, create_if_missing: bool = True) -> dict:
    payload = dict(result)
    work = sync_task_backing_work(db, project, payload, create_if_missing=create_if_missing)
    if work is not None:
        payload["work"] = work
    return payload


def _idle_managed_task_payload(result: dict) -> dict:
    """Translate legacy idle Task state into the current optional-managed-work contract."""
    if result.get("active"):
        return result
    raw_action = result.get("next_action")
    action = dict(raw_action) if isinstance(raw_action, dict) else {}
    if action.get("action") != "host_native":
        action = {
            "action": "host_native",
            "tool": None,
            "message": (
                "No managed Task is active. Ordinary work remains host-native. If the user explicitly "
                "asked for a managed Task or standard Task protocol, call task_create directly; AI Layer creates "
                "or links the backing Work automatically."
            ),
            "managed_option": {
                "tool": "task_create",
                "required": ["goal"],
                "optional": [
                    "acceptance_criteria",
                    "constraints",
                    "workflow",
                    "risk",
                    "cost_policy",
                ],
            },
            "worktree_rule": (
                "Pre-existing user changes are valid. Do not stash/reset/restore/commit merely to create or avoid a Task."
            ),
        }
    payload: dict[str, Any] = {
        "active": False,
        "state": result.get("state") or "no_active_task",
        "next_action": action,
    }
    for key in ("project_root", "preexisting_changes", "known_preexisting_state"):
        if result.get(key) not in (None, {}, []):
            payload[key] = result[key]
    return with_envelope(payload, ENVELOPE_MANAGED_NEXT)


def _with_managed_next(result: dict) -> dict:
    payload = dict(result)
    payload.pop("agent_contract", None)
    payload.pop("orchestrator_contract", None)
    task = payload.get("task")
    if isinstance(task, dict):
        task = dict(task)
        task.pop("delegation_contract", None)
        payload["task"] = task
    return with_envelope(payload, ENVELOPE_MANAGED_NEXT)


def _delegate_envelopes(result: dict) -> dict:
    """MCP-facing task_stage_delegate: orchestrator next_action plus slim worker packet."""
    raw_contract = result.get("delegation_contract")
    contract = raw_contract if isinstance(raw_contract, dict) else {}
    raw_handoff = result.get("orchestrator_handoff")
    handoff = raw_handoff if isinstance(raw_handoff, dict) else {}
    nested = handoff.get("delegation_contract")
    source = contract or (nested if isinstance(nested, dict) else {})
    raw_stage = result.get("active_stage")
    stage = raw_stage if isinstance(raw_stage, dict) else {}
    raw_next = result.get("next_action")
    next_action = raw_next if isinstance(raw_next, dict) else {}
    worker = worker_job_packet(source)
    stage_kind = str(
        stage.get("kind") or worker.get("stage") or next_action.get("stage") or "implement"
    )
    worker_id = stage.get("worker_id") or next_action.get("worker_id") or handoff.get("worker_id")
    stage_instruction = next_action.get("orchestrator_contract")
    if not isinstance(stage_instruction, dict):
        stage_instruction = orchestrator_stage_instruction(
            stage_kind=stage_kind,
            delegated=True,
            worker_id=str(worker_id) if worker_id else None,
        )
    start_action = handoff.get("next_host_action") or "START_THE_DELEGATED_WORKER_NOW"
    payload = {
        "active": True,
        "task": {
            "id": result.get("id"),
            "key": result.get("key"),
            "status": result.get("status"),
        },
        "orchestrator": {
            "next_action": {
                "action": start_action,
                "tool": None,
                "stage": stage_kind,
                "stage_id": stage.get("id") or worker.get("stage_id"),
                "worker_id": worker_id,
                "orchestrator_contract": stage_instruction,
            }
        },
        "worker": worker,
    }
    if result.get("delegation_idempotent"):
        payload["delegation_idempotent"] = True
    return with_envelope(payload, ENVELOPE_MANAGED_NEXT)


def _with_project_map_hint(result: dict) -> dict:
    payload = dict(result)
    task = payload.get("task") if isinstance(payload.get("task"), dict) else payload
    if str((task or {}).get("status") or "") != "completed":
        return payload
    payload["project_map_reconciliation"] = {
        "tool": "project_map_reconcile",
        "source_task_key": (task or {}).get("key"),
        "required_when": (
            "This Task materially established, changed, corrected or invalidated navigation knowledge."
        ),
        "skip_when": (
            "MICRO/cosmetic/local work produced no useful new navigation facts. Do not manufacture map text."
        ),
        "scope": (
            "Only paths actually inspected, understood or materially affected by this Task; never rescan unrelated areas."
        ),
    }
    return payload


def read_state(project_root: str | Path, *, include_history: bool = True) -> dict:
    """Read cheap durable Task state for projections.

    This query boundary intentionally does not call the authoritative Task navigator. `task_next`
    may inspect repository state to enforce provenance/drift guards; a Dashboard refresh must never
    trigger those repository scans. Database state is authoritative. The disk projection is a
    degraded-read fallback only and does not invent transitions when the database is unavailable.
    """
    resolved = Path(project_root).expanduser().resolve()
    database_error: str | None = None
    try:
        with session_scope() as db:
            project = _project(db, resolved)
            state = current_task(db, project, include_history=include_history)
            current_payload = dict(state.get("task") or {}) if state.get("active") else None
            latest_payload = current_payload or state.get("latest")
            projected_next_action = state.get("next_action") or (
                (current_payload or latest_payload or {}).get("next_action")
            )
            if current_payload is None:
                projected_next_action = _idle_managed_task_payload(
                    {"active": False, "next_action": projected_next_action}
                )["next_action"]
            return {
                "current": current_payload,
                "latest": latest_payload,
                "next_action": projected_next_action,
                "source": "database",
            }
    except Exception as exc:
        database_error = f"{type(exc).__name__}: {exc}"

    root = project_state_path(resolved, "tasks")
    current_payload = read_json(root / "current.json")
    latest_payload = read_json(root / "latest.json")
    fallback = current_payload or latest_payload or {}
    next_action = fallback.get("next_action")
    if current_payload is None:
        next_action = _idle_managed_task_payload({"active": False, "next_action": next_action})[
            "next_action"
        ]
    payload = {
        "current": current_payload,
        "latest": latest_payload,
        "next_action": next_action,
        "source": "disk-fallback",
    }
    if database_error:
        payload["database_error"] = database_error
    return payload


def current(project_root: str | Path, *, include_history: bool = True) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = current_task(db, project, include_history=include_history)
        if not result.get("active"):
            return _idle_managed_task_payload(result)
        return _with_managed_next(_with_task_work(db, project, result))


def next_action(project_root: str | Path) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = next_task_action(db, project)
        if not result.get("active"):
            return _idle_managed_task_payload(result)
        return _with_managed_next(_with_task_work(db, project, result))


def cancel(project_root: str | Path, *, reason: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = cancel_task(db, project, reason=reason)
        return _with_task_work(db, project, result)


def worker_disconnected(project_root: str | Path, *, reason: str) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = recover_disconnected_worker(db, project, reason=reason)
        return _with_task_work(db, project, result)


def worker_heartbeat(
    project_root: str | Path,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> dict:
    with session_scope() as db:
        return heartbeat_worker(
            db,
            _project(db, project_root),
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )


def reap_stale_workers() -> dict:
    with session_scope() as db:
        return reap_stale_worker_leases(db)


def resume(project_root: str | Path) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = resume_task(db, project)
        return _with_task_work(db, project, result)


def create(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = create_task(db, project, **kwargs)
        return _with_task_work(db, project, result, create_if_missing=True)


def adopt(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = adopt_task(db, project, **kwargs)
        return _with_task_work(db, project, result, create_if_missing=True)


def delegate(
    project_root: str | Path,
    *,
    worker_id: str,
    actual_model: str | None = None,
    model_assurance: str = "requested_unverified",
    telemetry: dict | None = None,
) -> dict:
    with session_scope() as db:
        result = delegate_current_stage(
            db,
            _project(db, project_root),
            worker_id=worker_id,
            actual_model=actual_model,
            model_assurance=model_assurance,
            telemetry=telemetry,
        )
        return _delegate_envelopes(result)


def complete_current(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = complete_current_stage(db, project, **kwargs)
        return _with_project_map_hint(_with_task_work(db, project, result))


def complete_legacy(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        project = _project(db, project_root)
        result = complete_stage(db, project, **kwargs)
        return _with_project_map_hint(_with_task_work(db, project, result))


def prepare_review_sandbox(project_root: str | Path) -> dict:
    with session_scope() as db:
        return prepare_current_review_sandbox(db, _project(db, project_root))


def run_review_check(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        return run_current_review_check(db, _project(db, project_root), **kwargs)


def cleanup_review_sandbox(project_root: str | Path) -> dict:
    with session_scope() as db:
        return cleanup_current_review_sandbox(db, _project(db, project_root))
