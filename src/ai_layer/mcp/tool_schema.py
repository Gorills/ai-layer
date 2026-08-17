"""MCP JSON-schema constraints that match current runtime validation bounds."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkKind = Literal["change", "diagnose", "review", "research", "planning", "ops"]
WorkCheckStatus = Literal["passed", "failed", "skipped", "blocked", "not_run", "reported"]
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


def _natural_check_status(
    value: object, *, result: object, summary: str, command: str | None
) -> WorkCheckStatus:
    rendered = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases: dict[str, WorkCheckStatus] = {
        "pass": "passed",
        "passed": "passed",
        "success": "passed",
        "succeeded": "passed",
        "ok": "passed",
        "fail": "failed",
        "failed": "failed",
        "failure": "failed",
        "error": "failed",
        "skipped": "skipped",
        "skip": "skipped",
        "blocked": "blocked",
        "not_run": "not_run",
        "reported": "reported",
    }
    if rendered:
        return aliases.get(rendered, "reported")
    if isinstance(result, bool):
        return "passed" if result else "failed"
    if isinstance(result, int):
        return "passed" if result == 0 else "failed"
    evidence = " ".join(str(result if result is not None else summary).strip().casefold().split())
    if not evidence:
        return "reported" if command else "not_run"
    if any(marker in evidence for marker in ("not run", "not executed", "not checked")):
        return "not_run"
    if "blocked" in evidence:
        return "blocked"
    if "skipped" in evidence:
        return "skipped"
    if any(
        marker in evidence
        for marker in ("no errors", "no error", "no failures", "passed", "success", "succeeded")
    ):
        return "passed"
    if any(marker in evidence for marker in ("failed", "failure", " error", "errors")):
        return "failed"
    return "reported"


class WorkCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(max_length=240)] | None = None
    status: WorkCheckStatus | None = None
    summary: Annotated[str, Field(max_length=500)] = ""
    command: Annotated[str | None, Field(max_length=2000, exclude=True)] = None
    result: Annotated[str | bool | int | None, Field(exclude=True)] = None

    @model_validator(mode="after")
    def normalize_natural_report(self) -> WorkCheckInput:
        self.name = str(self.name or "").strip() or "reported check"
        if not self.summary and self.result is not None:
            self.summary = str(self.result).strip()[:500]
        self.status = _natural_check_status(
            self.status, result=self.result, summary=self.summary, command=self.command
        )
        return self


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
