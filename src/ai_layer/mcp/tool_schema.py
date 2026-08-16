"""MCP JSON-schema constraints that match current runtime validation bounds."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

WorkKind = Literal["change", "diagnose", "review", "research", "planning", "ops"]
WorkCheckStatus = Literal["passed", "failed", "skipped", "blocked", "not_run"]
WorkMapStatus = Literal[
    "reconciled",
    "checked_no_change",
    "not_applicable",
    "deferred",
    "pending",
]
TaskWorkflow = Literal["auto", "micro", "standard", "discovery_first", "analysis_only"]
TaskScale = Literal["auto", "low", "normal", "high"]
TaskCostPolicy = Literal["auto", "economy", "balanced", "quality"]
KnowledgeStatus = Literal["VERIFIED", "DRAFT", "STALE", "SUPERSEDED"]
KnowledgeCategory = Literal[
    "overview",
    "subsystem",
    "runtime",
    "data",
    "integration",
    "deployment",
    "testing",
    "invariant",
    "fragile-area",
    "other",
]
SkillScope = Literal["global", "project"]

WorkGoalText = Annotated[str, Field(min_length=1, max_length=2000)]
WorkSummaryText = Annotated[str, Field(min_length=1, max_length=4000)]
WorkSummaryOptional = Annotated[str, Field(max_length=4000)]
WorkKeyText = Annotated[str, Field(min_length=3, max_length=16)]
WorkHostText = Annotated[str, Field(max_length=64)]
WorkClientText = Annotated[str, Field(max_length=64)]
WorkSessionText = Annotated[str, Field(max_length=128)]
WorkLinkKey = Annotated[str, Field(max_length=16)]
IdempotencyKey = Annotated[str, Field(max_length=128)]
ProjectPathText = Annotated[str, Field(min_length=1, max_length=512)]
ProjectPathList = Annotated[list[ProjectPathText], Field(max_length=120)]
TaskGoalText = Annotated[str, Field(min_length=1, max_length=8000)]
SearchQueryText = Annotated[str, Field(min_length=1)]
SearchLimit = Annotated[int, Field(ge=1, le=20)]
SkillSearchLimit = Annotated[int, Field(ge=1, le=30)]
KnowledgeListLimit = Annotated[int, Field(ge=1, le=200)]
SessionListLimit = Annotated[int, Field(ge=1, le=50)]
MemoryContextLimit = Annotated[int, Field(ge=1, le=12)]
QueryVariantList = Annotated[list[SearchQueryText], Field(max_length=1)]
KnowledgeTitleText = Annotated[str, Field(min_length=1, max_length=180)]
KnowledgeSummaryText = Annotated[str, Field(min_length=1, max_length=2200)]
KnowledgeKeyText = Annotated[str, Field(min_length=1, max_length=160)]


class WorkCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=240)]
    status: WorkCheckStatus
    summary: Annotated[str, Field(max_length=500)] = ""


class WorkRepositoryDeltaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: Annotated[str, Field(max_length=128)] | None = None
    final_revision: Annotated[str, Field(max_length=128)] | None = None
    changed_files: Annotated[int, Field(ge=0)] | None = None
    insertions: Annotated[int, Field(ge=0)] | None = None
    deletions: Annotated[int, Field(ge=0)] | None = None
    dirty: bool | None = None
    assurance: (
        Literal[
            "ai_layer_observed",
            "host_reported",
            "agent_reported",
            "inferred_unattributed",
            "requested_unverified",
        ]
        | None
    ) = None


class WorkMapDispositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: WorkMapStatus
    scope: ProjectPathList = Field(default_factory=list)
    scope_paths: ProjectPathList | None = None
    reason: Annotated[str, Field(max_length=500)] = ""
    event_id: Annotated[str, Field(max_length=64)] | None = None


WorkCheckList = Annotated[list[WorkCheckInput], Field(max_length=40)]
