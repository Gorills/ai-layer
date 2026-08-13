from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_layer.core.paths import project_state_path
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.domain.agent_contract import agent_runtime_contract
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


def _idle_managed_task_payload(result: dict) -> dict:
    """Translate legacy idle Task state into the current optional-managed-work contract."""
    if result.get("active"):
        return result
    payload = dict(result)
    payload["next_action"] = {
        "action": "host_native",
        "tool": None,
        "message": (
            "No managed Task is active. Continue ordinary work through the host-native agent runtime; "
            "a managed Task is not required. Create one only when the user or task needs durable/strict "
            "managed execution."
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
    payload["agent_contract"] = agent_runtime_contract()
    return payload


def _with_agent_contract(result: dict) -> dict:
    payload = dict(result)
    payload["agent_contract"] = agent_runtime_contract()
    return payload


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
        result = current_task(db, _project(db, project_root), include_history=include_history)
        if not result.get("active"):
            return _idle_managed_task_payload(result)
        return _with_agent_contract(result)


def next_action(project_root: str | Path) -> dict:
    with session_scope() as db:
        result = next_task_action(db, _project(db, project_root))
        if not result.get("active"):
            return _idle_managed_task_payload(result)
        return _with_agent_contract(result)


def cancel(project_root: str | Path, *, reason: str) -> dict:
    with session_scope() as db:
        return cancel_task(db, _project(db, project_root), reason=reason)


def worker_disconnected(project_root: str | Path, *, reason: str) -> dict:
    with session_scope() as db:
        return recover_disconnected_worker(db, _project(db, project_root), reason=reason)


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
        return resume_task(db, _project(db, project_root))


def create(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        return create_task(db, _project(db, project_root), **kwargs)


def adopt(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        return adopt_task(db, _project(db, project_root), **kwargs)


def delegate(
    project_root: str | Path,
    *,
    worker_id: str,
    actual_model: str | None = None,
    model_assurance: str = "requested_unverified",
    telemetry: dict | None = None,
) -> dict:
    with session_scope() as db:
        return delegate_current_stage(
            db,
            _project(db, project_root),
            worker_id=worker_id,
            actual_model=actual_model,
            model_assurance=model_assurance,
            telemetry=telemetry,
        )


def complete_current(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        result = complete_current_stage(db, _project(db, project_root), **kwargs)
        return _with_project_map_hint(result)


def complete_legacy(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        result = complete_stage(db, _project(db, project_root), **kwargs)
        return _with_project_map_hint(result)


def prepare_review_sandbox(project_root: str | Path) -> dict:
    with session_scope() as db:
        return prepare_current_review_sandbox(db, _project(db, project_root))


def run_review_check(project_root: str | Path, **kwargs: Any) -> dict:
    with session_scope() as db:
        return run_current_review_check(db, _project(db, project_root), **kwargs)


def cleanup_review_sandbox(project_root: str | Path) -> dict:
    with session_scope() as db:
        return cleanup_current_review_sandbox(db, _project(db, project_root))
