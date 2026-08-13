from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ai_layer.dashboard.activity_contracts import ActivityRead
from ai_layer.dashboard.error_contracts import DASHBOARD_QUERY_RESPONSES
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.projections.dashboard_activity import activity_payload

router = APIRouter(tags=["dashboard"])


def _query_error(exc: ValueError, project_key: str | None) -> HTTPException:
    error = StructuredError(
        code=ErrorCode.VALIDATION_FAILED,
        category=ErrorCategory.VALIDATION,
        message=str(exc),
        retryable=True,
        required_action="Use documented activity filters and an unmodified cursor.",
        ids={"project_key": str(project_key)},
    )
    return HTTPException(status_code=422, detail=error.to_dict())


@router.get(
    "/activity",
    response_model=ActivityRead,
    responses=DASHBOARD_QUERY_RESPONSES,
)
def dashboard_activity(
    project_key: str | None = None,
    mode: str = "milestones",
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    work_id: UUID | None = None,
    task_id: UUID | None = None,
    epic_id: UUID | None = None,
    actor_id: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    importance: str | None = None,
    assurance: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
):
    try:
        payload = activity_payload(
            project_key_value=project_key,
            mode=mode,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            work_id=work_id,
            task_id=task_id,
            epic_id=epic_id,
            actor_id=actor_id,
            event_type=event_type,
            status=status,
            importance=importance,
            assurance=assurance,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise _query_error(exc, project_key) from exc
    if payload is None:
        error = StructuredError(
            code=ErrorCode.VALIDATION_FAILED,
            category=ErrorCategory.VALIDATION,
            message="Registered project not found.",
            retryable=True,
            required_action="Use keys returned by the dashboard APIs.",
            ids={"project_key": str(project_key)},
        )
        raise HTTPException(status_code=404, detail=error.to_dict())
    return payload
