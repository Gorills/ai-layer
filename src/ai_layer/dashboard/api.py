from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.projections.dashboard import overview_payload, project_payload
from ai_layer.projections.epics import epic_detail_payload, project_epics_payload

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _not_found(ids: dict[str, str], message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=StructuredError(
            code=ErrorCode.VALIDATION_FAILED,
            category=ErrorCategory.VALIDATION,
            message=message,
            retryable=True,
            required_action="Use project/Epic keys returned by the dashboard APIs.",
            ids=ids,
        ).to_dict(),
    )


@router.get("/overview")
def dashboard_overview():
    return overview_payload()


@router.get("/projects/{project_key}")
def dashboard_project(project_key: str):
    payload = project_payload(project_key)
    if payload is None:
        raise _not_found({"project_key": project_key}, "Registered project not found.")
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
