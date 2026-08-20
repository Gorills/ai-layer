from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_layer.application.commands import execute_idempotent
from ai_layer.core.request_context import current_operation
from ai_layer.core.service import get_project
from ai_layer.db.session import session_scope
from ai_layer.domain.agent_contract import ENVELOPE_ORDINARY, with_envelope
from ai_layer.domain.security import SYSTEM_ACTOR
from ai_layer.observability.work_events import append_contextual_event
from ai_layer.work.lifecycle import resume_work, wait_work
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


def _bound_result(project: Any, payload: dict) -> dict:
    return with_envelope(
        {
            **payload,
            "project_root": str(Path(project.root_path).expanduser().resolve()),
        },
        ENVELOPE_ORDINARY,
    )


def _effective_work_payload(item: dict) -> dict:
    result = dict(item)
    if result.get("status") == "active" and not any(
        run.get("status") == "active" for run in result.get("runs") or []
    ):
        result["status"] = "awaiting_feedback"
    return result


def _mutation_result(
    project: Any,
    db: Any,
    work: Any,
    *,
    root_run: Any | None = None,
    effective_status: bool = False,
) -> dict:
    work_payload = work_to_dict(db, work, include_runs=False)
    if effective_status:
        work_payload = _effective_work_payload(work_payload)
    work_payload.pop("runs", None)
    payload = {"work": work_payload}
    if root_run is not None:
        payload["root_run"] = run_to_dict(root_run)
    return _bound_result(project, payload)


def _compact_work_payload(item: dict) -> dict:
    disposition = dict(item.get("map_disposition") or {}) or {"status": "pending"}
    return {
        "id": item.get("id"),
        "key": item.get("key"),
        "goal": item.get("goal"),
        "kind": item.get("kind"),
        "status": item.get("status"),
        "live": bool(item.get("live")),
        "map_disposition": {"status": disposition.get("status", "pending")},
        "map_pending": disposition.get("status") == "pending",
        "updated_at": item.get("updated_at"),
    }


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
            return _mutation_result(project, db, work, root_run=run)

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
    work_key: str | None,
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
            return _mutation_result(project, db, work, root_run=run)

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


def wait(
    project_root: str | Path,
    *,
    work_key: str | None,
    summary: str = "",
    idempotency_key: str | None = None,
) -> dict:
    actor, correlation_id = _command_context()
    with session_scope() as db:
        project = get_project(db, project_root)
        request = {"work_key": work_key, "summary": summary}

        def handler() -> dict:
            work, runs = wait_work(
                db,
                project,
                work_key_value=work_key,
                summary=summary,
            )
            root_run = next((item for item in runs if item.role == "root"), None)
            append_contextual_event(
                db,
                event_type="WorkAwaitingFeedback",
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
                payload={"status": "awaiting_feedback", "summary": work.result_summary},
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
            return _mutation_result(project, db, work, root_run=root_run, effective_status=True)

        return execute_idempotent(
            db,
            command_id=_command_id(idempotency_key),
            command_name="work_wait",
            request=request,
            actor=actor,
            correlation_id=correlation_id,
            project_id=project.id,
            handler=handler,
        )


def resume(
    project_root: str | Path,
    *,
    work_key: str | None,
    idempotency_key: str | None = None,
    **kwargs: Any,
) -> dict:
    actor, correlation_id = _command_context()
    with session_scope() as db:
        project = get_project(db, project_root)
        request = {"work_key": work_key, **kwargs}

        def handler() -> dict:
            work, run = resume_work(db, project, work_key_value=work_key, **kwargs)
            append_contextual_event(
                db,
                event_type="WorkResumed",
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
                payload={"status": work.status},
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
            return _mutation_result(project, db, work, root_run=run)

        return execute_idempotent(
            db,
            command_id=_command_id(idempotency_key),
            command_name="work_resume",
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
    work_key: str | None,
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
            return _mutation_result(project, db, work, root_run=root_run)

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
    work_key: str | None,
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
    work_key: str | None,
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
    work_key: str | None,
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
    work_key: str | None,
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


def _attention_work(active: list[dict], recent: list[dict]) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for item in [
        *[
            row
            for row in active
            if row.get("status") == "blocked"
            or (row.get("status") == "active" and not row.get("live"))
        ],
        *[
            row
            for row in recent
            if (row.get("map_disposition") or {}).get("status") in {"pending", "deferred"}
        ],
    ]:
        key = str(item.get("id") or item.get("key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def state(project_root: str | Path, *, limit: int = 8, compact: bool = False) -> dict:
    with session_scope() as db:
        project = get_project(db, project_root)
        active_full = [
            _effective_work_payload(item)
            for item in list_work(db, project, active_only=True, limit=50, compact=False)
        ]
        all_recent = [
            _effective_work_payload(item)
            for item in list_work(db, project, active_only=False, limit=limit, compact=False)
        ]
        recent_full = [
            item
            for item in all_recent
            if item["status"] not in {"active", "blocked", "awaiting_feedback"}
        ]
        if compact:
            active = [_compact_work_payload(item) for item in active_full]
            recent = [_compact_work_payload(item) for item in recent_full]
        else:
            active = active_full
            recent = recent_full
        bounded_recent = recent[: max(1, min(limit, 20))]
        return {
            "active": active,
            "recent": bounded_recent,
            "live": [item for item in active if item.get("live")],
            "attention": _attention_work(active, bounded_recent),
            "observability_contract": (
                "WorkItems are durable user-work records. live=true requires a non-stale observed AgentRun; "
                "awaiting_feedback is an open WorkItem with no active AgentRun; managed Tasks and MCP bridges "
                "alone never prove that native work is active."
            ),
        }
