from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, RootModel


class StructuredErrorRead(BaseModel):
    code: str
    category: str
    message: str
    retryable: bool
    required_action: str | None
    ids: dict[str, str] | None
    details: dict[str, Any] | None


class StructuredErrorEnvelope(BaseModel):
    detail: StructuredErrorRead


class ValidationIssueRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    loc: list[str | int]
    msg: str
    input: Any | None = None


class RequestValidationErrorEnvelope(BaseModel):
    detail: list[ValidationIssueRead]


class DashboardValidationError(RootModel[StructuredErrorEnvelope | RequestValidationErrorEnvelope]):
    pass


DASHBOARD_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": StructuredErrorEnvelope}
}
DASHBOARD_QUERY_RESPONSES: dict[int | str, dict[str, Any]] = {
    **DASHBOARD_NOT_FOUND_RESPONSES,
    422: {"model": DashboardValidationError},
}
