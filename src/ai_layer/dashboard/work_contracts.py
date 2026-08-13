from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_layer.dashboard.event_contracts import SafeEventPayload


class WorkRunRead(BaseModel):
    id: str
    parent_run_id: str | None
    role: str
    status: str
    effective_status: str
    stale: bool
    host: str
    client: str
    session_id: str
    turn_id: str
    model: str
    last_meaningful_action: str
    observability_coverage: str
    assurance: str
    started_at: str
    heartbeat_at: str
    ended_at: str | None


class WorkProjectRead(BaseModel):
    key: str
    name: str
    root: str


class WorkItemRead(BaseModel):
    id: str
    key: str
    goal: str
    kind: str
    status: str
    live: bool
    result_summary: str
    reviewed_paths: list[str]
    changed_paths: list[str]
    repository_delta: dict[str, Any]
    checks: list[dict[str, Any]]
    map_disposition: dict[str, Any]
    map_pending: bool
    observability_coverage: str
    assurance: str
    linked_task_id: str | None
    linked_epic_id: str | None
    linked_task_key: str | None = None
    linked_epic_key: str | None = None
    legacy_session_id: str | None
    started_at: str
    updated_at: str
    last_milestone_at: str
    completed_at: str | None
    runs: list[WorkRunRead]
    project: WorkProjectRead | None = None


class WorkPaginationRead(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int
    has_previous: bool
    has_next: bool


class WorkListRead(BaseModel):
    contract_version: int = Field(1, frozen=True)
    generated_at: str
    items: list[WorkItemRead]
    pagination: WorkPaginationRead
    projects: list[dict[str, Any]]
    filters: dict[str, str | None]
    ordering: list[str]


class WorkTimelineEventRead(BaseModel):
    event_id: str
    event_type: str
    project_id: str | None
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
    payload: SafeEventPayload
    occurred_at: str


class WorkDetailRead(BaseModel):
    contract_version: int = Field(1, frozen=True)
    project: WorkProjectRead
    work: WorkItemRead
    timeline: list[WorkTimelineEventRead]
    timeline_total: int
    timeline_truncated: bool
    timeline_ordering: list[str]
