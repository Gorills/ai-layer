from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError
from ai_layer.projections.dashboard import overview_payload, project_payload

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/overview")
def dashboard_overview():
    return overview_payload()


@router.get("/projects/{project_key}")
def dashboard_project(project_key: str):
    payload = project_payload(project_key)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=StructuredError(
                code=ErrorCode.VALIDATION_FAILED,
                category=ErrorCategory.VALIDATION,
                message="Registered project not found.",
                retryable=True,
                required_action="Use a project key returned by the dashboard overview/project registry.",
                ids={"project_key": project_key},
            ).to_dict(),
        )
    return payload
