from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.projections.dashboard import overview_payload, project_payload
from ai_layer.projections.dashboard_activity import activity_payload
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
from ai_layer.projections.epics import epic_detail_payload, epics_payload, project_epics_payload

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


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


@router.get("/overview")
def dashboard_overview():
    return overview_payload()


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


@router.get("/activity")
def dashboard_activity(
    project_key: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    payload = activity_payload(
        project_key_value=project_key,
        page=page,
        page_size=page_size,
    )
    if payload is None:
        raise _not_found({"project_key": str(project_key)}, "Registered project not found.")
    return payload


@router.get("/projects/{project_key}")
def dashboard_project(project_key: str):
    payload = project_payload(project_key)
    if payload is None:
        raise _not_found({"project_key": project_key}, "Registered project not found.")
    epics = project_epics_payload(project_key) or {}
    project = payload.get("project") or {}
    project["intelligence"] = project_intelligence_summary(
        project.get("root") or "",
        task_state=payload.get("task_state") or {},
        epics=epics.get("epics") or [],
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
