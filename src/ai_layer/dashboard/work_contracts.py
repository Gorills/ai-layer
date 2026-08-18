from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel

from ai_layer.dashboard.event_contracts import SafeEventPayload

WorkKind = Literal["change", "diagnose", "review", "research", "planning", "ops"]
WorkStatus = Literal[
    "active",
    "awaiting_feedback",
    "blocked",
    "completed",
    "failed",
    "interrupted",
    "abandoned",
]
WorkRunStatus = Literal["active", "completed", "failed", "interrupted", "abandoned"]
WorkRunEffectiveStatus = Literal[
    "active",
    "completed",
    "failed",
    "interrupted",
    "abandoned",
    "stale",
]
WorkObservability = Literal[
    "full_host_hooks",
    "lifecycle_only",
    "control_plane_only",
    "inferred_repository_delta",
    "unavailable",
]
WorkAssurance = Literal[
    "ai_layer_observed",
    "host_reported",
    "agent_reported",
    "inferred_unattributed",
    "requested_unverified",
]
WorkCheckStatus = Literal["passed", "failed", "skipped", "blocked", "not_run"]
WorkMapStatus = Literal[
    "reconciled",
    "checked_no_change",
    "not_applicable",
    "deferred",
    "pending",
]
ProjectMode = Literal["standard", "external", "strict-private"]
ProjectProvenance = Literal["allow", "forbid"]


class WorkCheckRead(TypedDict, total=False):
    name: str
    status: WorkCheckStatus
    summary: str


class WorkRepositoryDeltaRead(TypedDict, total=False):
    base_revision: str
    final_revision: str
    changed_files: int
    insertions: int
    deletions: int
    dirty: bool
    assurance: WorkAssurance


class WorkMapDispositionRead(TypedDict, total=False):
    status: WorkMapStatus
    scope: list[str]
    reason: str
    event_id: str | None


class WorkRunRead(BaseModel):
    id: str
    parent_run_id: str | None
    role: Literal["root", "subagent"]
    status: WorkRunStatus
    effective_status: WorkRunEffectiveStatus
    stale: bool
    host: str
    client: str
    session_id: str
    turn_id: str
    model: str
    last_meaningful_action: str
    observability_coverage: WorkObservability
    assurance: WorkAssurance
    started_at: str
    heartbeat_at: str
    ended_at: str | None


class WorkProjectRead(BaseModel):
    key: str
    name: str
    root: str


class WorkProjectOptionRead(BaseModel):
    key: str
    name: str = ""
    root: str = ""
    mode: ProjectMode = "standard"
    provenance: ProjectProvenance = "allow"


class WorkItemRead(BaseModel):
    id: str
    key: str
    goal: str
    kind: WorkKind
    status: WorkStatus
    live: bool
    result_summary: str
    reviewed_paths: list[str]
    changed_paths: list[str]
    repository_delta: WorkRepositoryDeltaRead
    checks: list[WorkCheckRead]
    map_disposition: WorkMapDispositionRead
    map_pending: bool
    observability_coverage: WorkObservability
    assurance: WorkAssurance
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


class WorkListFiltersRead(BaseModel):
    project_key: str | None
    status: WorkStatus | None


class WorkListRead(BaseModel):
    contract_version: Literal[1]
    generated_at: str
    items: list[WorkItemRead]
    pagination: WorkPaginationRead
    projects: list[WorkProjectOptionRead]
    filters: WorkListFiltersRead
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
    importance: Literal["low", "normal", "high"]
    payload: SafeEventPayload
    occurred_at: str


class WorkDetailRead(BaseModel):
    contract_version: Literal[1]
    project: WorkProjectRead
    work: WorkItemRead
    timeline: list[WorkTimelineEventRead]
    timeline_total: int
    timeline_truncated: bool
    timeline_ordering: list[str]
