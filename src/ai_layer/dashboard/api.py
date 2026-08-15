from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ai_layer.dashboard.activity_api import router as activity_router
from ai_layer.dashboard.error_contracts import (
    DASHBOARD_NOT_FOUND_RESPONSES,
    DASHBOARD_QUERY_RESPONSES,
)
from ai_layer.dashboard.work_contracts import WorkDetailRead, WorkListRead, WorkStatus
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.projections.dashboard import overview_payload, project_payload
from ai_layer.projections.dashboard_intelligence import project_intelligence_summary
from ai_layer.projections.dashboard_monitoring import monitoring_payload
from ai_layer.projections.dashboard_reference import (
    knowledge_detail_payload,
    knowledge_payload,
    rules_payload,
    skill_detail_payload,
    skills_payload,
)
from ai_layer.projections.dashboard_tasks import task_detail_payload, tasks_payload
from ai_layer.projections.dashboard_work import (
    work_detail_payload,
    work_items_payload,
)
from ai_layer.projections.dashboard_work_state import enrich_overview, enrich_project
from ai_layer.projections.epics import epic_detail_payload, epics_payload, project_epics_payload

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
router.include_router(activity_router)


def _not_found(ids: dict[str, str], message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=StructuredError(
            code=ErrorCode.VALIDATION_FAILED,
            category=ErrorCategory.VALIDATION,
            message=message,
            retryable=True,
            required_action="Use keys returned by the dashboard APIs.",
            ids=ids,
        ).to_dict(),
    )


def _invalid_query(exc: ValueError, *, action: str, ids: dict[str, str]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=StructuredError(
            code=ErrorCode.VALIDATION_FAILED,
            category=ErrorCategory.VALIDATION,
            message=str(exc),
            retryable=True,
            required_action=action,
            ids=ids,
        ).to_dict(),
    )


def _project_epics_best_effort(project_key: str) -> list[dict]:
    """Keep the project page readable when durable Epic storage is temporarily unavailable."""
    try:
        payload = project_epics_payload(project_key) or {}
    except Exception:
        return []
    return list(payload.get("epics") or [])


@router.get("/overview")
def dashboard_overview():
    return enrich_overview(overview_payload())


@router.get("/work", response_model=WorkListRead, responses=DASHBOARD_QUERY_RESPONSES)
def dashboard_work_items(
    project_key: str | None = None,
    status: WorkStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    try:
        payload = work_items_payload(
            project_key_value=project_key,
            status=status,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise _invalid_query(
            exc,
            action="Use a documented Work status filter.",
            ids={"status": str(status)},
        ) from exc
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get(
    "/work/{project_key}/{work_key}",
    response_model=WorkDetailRead,
    responses=DASHBOARD_NOT_FOUND_RESPONSES,
)
def dashboard_work_item(project_key: str, work_key: str):
    payload = work_detail_payload(project_key, work_key)
    if payload is None:
        raise _not_found(
            {"project_key": project_key, "work_key": work_key},
            "Work item not found for this project.",
        )
    return payload


@router.get("/tasks")
def dashboard_tasks(
    project_key: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    payload = tasks_payload(
        project_key_value=project_key,
        status=status,
        page=page,
        page_size=page_size,
    )
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get("/tasks/{project_key}/{task_key}")
def dashboard_task(project_key: str, task_key: str):
    payload = task_detail_payload(project_key, task_key)
    if payload is None:
        raise _not_found(
            {"project_key": project_key, "task_key": task_key},
            "Task not found for this project.",
        )
    return payload


@router.get("/epics")
def dashboard_epics(
    project_key: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    payload = epics_payload(
        project_key_value=project_key,
        status=status,
        page=page,
        page_size=page_size,
    )
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get("/skills")
def dashboard_skills(
    project_key: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    payload = skills_payload(
        project_key_value=project_key,
        page=page,
        page_size=page_size,
    )
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get("/skills/{slug}")
def dashboard_skill(slug: str, project_key: str | None = None):
    payload = skill_detail_payload(project_key, slug)
    if payload is None:
        ids = {"slug": slug}
        if project_key:
            ids["project_key"] = project_key
        raise _not_found(ids, "Skill not found in the selected catalog.")
    return payload


@router.get("/rules")
def dashboard_rules(project_key: str | None = None):
    payload = rules_payload(project_key)
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get("/knowledge/{project_key}")
def dashboard_knowledge(
    project_key: str,
    status: str | None = "VERIFIED",
    page: int = 1,
    page_size: int = 10,
):
    payload = knowledge_payload(
        project_key,
        status=status,
        page=page,
        page_size=page_size,
    )
    if payload is None:
        raise _not_found({"project_key": project_key}, "Registered project not found.")
    return payload


@router.get("/knowledge/{project_key}/{knowledge_id}")
def dashboard_knowledge_detail(project_key: str, knowledge_id: str):
    payload = knowledge_detail_payload(project_key, knowledge_id)
    if payload is None:
        raise _not_found(
            {"project_key": project_key, "knowledge_id": knowledge_id},
            "Knowledge card not found for this project.",
        )
    return payload


@router.get("/monitoring")
def dashboard_monitoring(project_key: str | None = None):
    payload = monitoring_payload(project_key)
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get("/projects/{project_key}")
def dashboard_project(project_key: str):
    payload = project_payload(project_key)
    if payload is None:
        raise _not_found({"project_key": project_key}, "Registered project not found.")
    payload = enrich_project(payload)
    project = payload.get("project") or {}
    project["intelligence"] = project_intelligence_summary(
        project.get("root") or "",
        task_state=payload.get("task_state") or {},
        epics=_project_epics_best_effort(project_key),
    )
    return payload


@router.get("/projects/{project_key}/epics")
def dashboard_project_epics(project_key: str):
    payload = project_epics_payload(project_key)
    if payload is None:
        raise _not_found({"project_key": project_key}, "Registered project not found.")
    return payload


@router.get("/projects/{project_key}/epics/{epic_key}")
def dashboard_epic(project_key: str, epic_key: str):
    payload = epic_detail_payload(project_key, epic_key)
    if payload is None:
        raise _not_found(
            {"project_key": project_key, "epic_key": epic_key},
            "Epic not found for this project.",
        )
    return payload
