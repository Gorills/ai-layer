from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_layer.dashboard.event_contracts import SafeEventPayload


class ActivityItemRead(BaseModel):
    event_id: str
    event_type: str
    project_id: str | None
    project_key: str
    project_name: str
    work_id: str | None
    run_id: str | None
    task_id: str | None
    epic_id: str | None
    correlation_id: str | None
    causation_id: str | None
    actor_id: str
    actor_kind: str
    interface: str
    host: str
    client: str
    session_id: str
    turn_id: str
    model: str
    retention_class: str
    importance: str
    assurance: str
    payload: SafeEventPayload
    occurred_at: str
    operation: str
    status: str
    duration_ms: int | float | None
    error_type: str | None


class ActivityFiltersRead(BaseModel):
    project_key: str | None
    mode: str
    occurred_after: str | None
    occurred_before: str | None
    work_id: str | None
    task_id: str | None
    epic_id: str | None
    actor_id: str | None
    event_type: str | None
    status: str | None
    importance: str | None
    assurance: str | None


class ActivityRead(BaseModel):
    contract_version: int = Field(2, frozen=True)
    generated_at: str
    items: list[ActivityItemRead]
    next_cursor: str | None
    has_more: bool
    limit: int
    projects: list[dict[str, Any]]
    filters: ActivityFiltersRead
    ordering: list[str]
    retention: str
