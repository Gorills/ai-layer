from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_layer.application.commands import execute_idempotent
from ai_layer.core.request_context import current_operation
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.domain.security import SYSTEM_ACTOR
from ai_layer.observability.work_events import append_contextual_event
from ai_layer.work.service import (
    begin_work,
    checkpoint_work,
    finish_work,
    list_work,
    run_to_dict,
    work_to_dict,
)


def _command_context() -> tuple[Any, str]:
    current = current_operation()
    return (
        (current.actor, current.correlation_id)
        if current is not None
        else (SYSTEM_ACTOR, uuid4().hex)
    )


def _command_id(value: str | None) -> str:
    rendered = str(value or "").strip()
    return rendered or uuid4().hex


def begin(project_root: str | Path, *, idempotency_key: str | None = None, **kwargs: Any) -> dict:
    actor, correlation_id = _command_context()
    with session_scope() as db:
        project = get_project(db, project_root)
        request = dict(kwargs)

        def handler() -> dict:
            work, run = begin_work(db, project, **kwargs)
            append_contextual_event(
                db,
                event_type="WorkStarted",
                project=project,
                aggregate_type="work",
                aggregate_id=str(work.id),
                work=work,
                run=run,
                host=run.host,
                client=run.client,
                session_id=run.session_id,
                turn_id=run.turn_id,
                model=run.model,
                payload={"goal": work.goal, "kind": work.kind, "status": work.status},
                importance="high",
            )
            append_contextual_event(
                db,
                event_type="AgentRunStarted",
                project=project,
                aggregate_type="agent_run",
                aggregate_id=str(run.id),
                work=work,
                run=run,
                host=run.host,
                client=run.client,
                session_id=run.session_id,
                turn_id=run.turn_id,
                model=run.model,
                payload={"status": run.status},
            )
            return {"work": work_to_dict(db, work), "root_run": run_to_dict(run)}

        return execute_idempotent(
            db,
            command_id=_command_id(idempotency_key),
            command_name="work_begin",
            request=request,
            actor=actor,
            correlation_id=correlation_id,
            project_id=project.id,
            handler=handler,
        )


def checkpoint(
    project_root: str | Path,
    *,
    work_key: str,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    actor, correlation_id = _command_context()
    with session_scope() as db:
        project = get_project(db, project_root)
        request = {"work_key": work_key, **kwargs}

        def handler() -> dict:
            work, run = checkpoint_work(db, project, work_key_value=work_key, **kwargs)
            append_contextual_event(
                db,
                event_type="WorkCheckpointed",
                project=project,
                aggregate_type="work",
                aggregate_id=str(work.id),
                work=work,
                run=run,
                host=run.host if run else "",
                client=run.client if run else "",
                session_id=run.session_id if run else "",
                turn_id=run.turn_id if run else "",
                model=run.model if run else "",
                payload={"status": work.status, "summary": work.result_summary},
            )
            return {"work": work_to_dict(db, work)}

        return execute_idempotent(
            db,
            command_id=_command_id(idempotency_key),
            command_name="work_checkpoint",
            request=request,
            actor=actor,
            correlation_id=correlation_id,
            project_id=project.id,
            handler=handler,
        )


def _finish(
    project_root: str | Path,
    *,
    command_name: str,
    event_type: str,
    status: str,
    work_key: str,
    summary: str,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    actor, correlation_id = _command_context()
    with session_scope() as db:
        project = get_project(db, project_root)
        request = {"work_key": work_key, "summary": summary, **kwargs}

        def handler() -> dict:
            work, runs = finish_work(
                db,
                project,
                work_key_value=work_key,
                status=status,
                summary=summary,
                **kwargs,
            )
            root_run = next((item for item in runs if item.role == "root"), None)
            append_contextual_event(
                db,
                event_type=event_type,
                project=project,
                aggregate_type="work",
                aggregate_id=str(work.id),
                work=work,
                run=root_run,
                host=root_run.host if root_run else "",
                client=root_run.client if root_run else "",
                session_id=root_run.session_id if root_run else "",
                turn_id=root_run.turn_id if root_run else "",
                model=root_run.model if root_run else "",
                payload={
                    "status": work.status,
                    "summary": work.result_summary,
                    "map_status": (work.map_disposition or {}).get("status", "pending"),
                },
                importance="high",
            )
            for run in runs:
                append_contextual_event(
                    db,
                    event_type="AgentRunStopped",
                    project=project,
                    aggregate_type="agent_run",
                    aggregate_id=str(run.id),
                    work=work,
                    run=run,
                    host=run.host,
                    client=run.client,
                    session_id=run.session_id,
                    turn_id=run.turn_id,
                    model=run.model,
                    payload={"status": run.status},
                )
            return {"work": work_to_dict(db, work)}

        return execute_idempotent(
            db,
            command_id=_command_id(idempotency_key),
            command_name=command_name,
            request=request,
            actor=actor,
            correlation_id=correlation_id,
            project_id=project.id,
            handler=handler,
        )


def complete(
    project_root: str | Path,
    *,
    work_key: str,
    summary: str,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    return _finish(
        project_root,
        command_name="work_complete",
        event_type="WorkCompleted",
        status="completed",
        work_key=work_key,
        summary=summary,
        idempotency_key=idempotency_key,
        **kwargs,
    )


def fail(
    project_root: str | Path,
    *,
    work_key: str,
    summary: str,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    return _finish(
        project_root,
        command_name="work_fail",
        event_type="WorkFailed",
        status="failed",
        work_key=work_key,
        summary=summary,
        idempotency_key=idempotency_key,
        **kwargs,
    )


def interrupt(
    project_root: str | Path,
    *,
    work_key: str,
    summary: str,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    return _finish(
        project_root,
        command_name="work_interrupt",
        event_type="WorkInterrupted",
        status="interrupted",
        work_key=work_key,
        summary=summary,
        idempotency_key=idempotency_key,
        **kwargs,
    )


def abandon(
    project_root: str | Path,
    *,
    work_key: str,
    summary: str,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    return _finish(
        project_root,
        command_name="work_abandon",
        event_type="WorkAbandoned",
        status="abandoned",
        work_key=work_key,
        summary=summary,
        idempotency_key=idempotency_key,
        **kwargs,
    )


def state(project_root: str | Path, *, limit: int = 8) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        active = list_work(db, project, active_only=True, limit=50)
        recent = [
            item
            for item in list_work(db, project, active_only=False, limit=limit)
            if item["status"] not in {"active", "blocked"}
        ]
        return {
            "active": active,
            "recent": recent[: max(1, min(limit, 20))],
            "live": [item for item in active if item.get("live")],
            "attention": [
                *[item for item in active if item.get("status") == "blocked"],
                *[
                    item
                    for item in recent
                    if (item.get("map_disposition") or {}).get("status") in {"pending", "deferred"}
                ],
            ],
            "observability_contract": (
                "WorkItems are durable user-work records. live=true requires a non-stale observed AgentRun; "
                "managed Tasks and MCP bridges alone never prove that native work is active."
            ),
        }
