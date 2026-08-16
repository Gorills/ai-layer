from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ai_layer.dashboard.event_contracts import SafeEventPayload
from ai_layer.dashboard.work_contracts import WorkAssurance, WorkProjectOptionRead

ActivityMode = Literal["milestones", "all"]
ActivityImportance = Literal["low", "normal", "high"]


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
    importance: ActivityImportance
    assurance: WorkAssurance
    payload: SafeEventPayload
    occurred_at: str
    operation: str
    status: str
    duration_ms: int | float | None
    error_type: str | None


class ActivityFiltersRead(BaseModel):
    project_key: str | None
    mode: ActivityMode
    occurred_after: str | None
    occurred_before: str | None
    work_id: str | None
    task_id: str | None
    epic_id: str | None
    actor_id: str | None
    event_type: str | None
    status: str | None
    importance: ActivityImportance | None
    assurance: WorkAssurance | None


class ActivityRead(BaseModel):
    contract_version: Literal[2]
    generated_at: str
    items: list[ActivityItemRead]
    next_cursor: str | None
    has_more: bool
    limit: int
    projects: list[WorkProjectOptionRead]
    filters: ActivityFiltersRead
    ordering: list[str]
    retention: str
