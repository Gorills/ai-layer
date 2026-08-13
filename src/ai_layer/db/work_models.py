from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ai_layer.db.base import Base
from ai_layer.db.models import utcnow

WORK_KINDS = ("change", "diagnose", "review", "research", "planning", "ops")
WORK_STATUSES = ("active", "blocked", "completed", "failed", "interrupted", "abandoned")
RUN_STATUSES = ("active", "completed", "failed", "interrupted", "abandoned")
OBSERVABILITY_COVERAGE = (
    "full_host_hooks",
    "lifecycle_only",
    "control_plane_only",
    "inferred_repository_delta",
    "unavailable",
)


class WorkItem(Base):
    """Durable user-visible unit of ordinary work, independent from managed Task assurance."""

    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_work_items_project_sequence"),
        Index("ix_work_items_project_status_updated", "project_id", "status", "updated_at"),
        CheckConstraint(
            "kind IN ('change','diagnose','review','research','planning','ops')",
            name="ck_work_items_kind",
        ),
        CheckConstraint(
            "status IN ('active','blocked','completed','failed','interrupted','abandoned')",
            name="ck_work_items_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    goal: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="change")
    status: Mapped[str] = mapped_column(String(16), default="active")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    reviewed_paths: Mapped[list] = mapped_column(JSON, default=list)
    changed_paths: Mapped[list] = mapped_column(JSON, default=list)
    repository_delta: Mapped[dict] = mapped_column(JSON, default=dict)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    map_disposition: Mapped[dict] = mapped_column(JSON, default=dict)
    observability_coverage: Mapped[str] = mapped_column(String(32), default="lifecycle_only")
    assurance: Mapped[str] = mapped_column(String(32), default="agent_reported")
    linked_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    linked_epic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("epics.id", ondelete="SET NULL"), nullable=True
    )
    legacy_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_milestone_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRun(Base):
    """Observed root-agent/subagent lifecycle attached to one WorkItem."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_work_status_heartbeat", "work_id", "status", "heartbeat_at"),
        CheckConstraint(
            "status IN ('active','completed','failed','interrupted','abandoned')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint("role IN ('root','subagent')", name="ck_agent_runs_role"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(16), default="root")
    status: Mapped[str] = mapped_column(String(16), default="active")
    host: Mapped[str] = mapped_column(String(64), default="unknown")
    client: Mapped[str] = mapped_column(String(64), default="unknown")
    session_id: Mapped[str] = mapped_column(String(128), default="")
    turn_id: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    last_meaningful_action: Mapped[str] = mapped_column(Text, default="")
    observability_coverage: Mapped[str] = mapped_column(String(32), default="lifecycle_only")
    assurance: Mapped[str] = mapped_column(String(32), default="agent_reported")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeEventContext(Base):
    """Additive correlation spine for RuntimeEvent without destabilizing historical event rows."""

    __tablename__ = "runtime_event_context"
    __table_args__ = (
        Index("ix_runtime_event_context_work", "work_id", "event_id"),
        Index("ix_runtime_event_context_run", "run_id", "event_id"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runtime_events.id", ondelete="CASCADE"), primary_key=True
    )
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    epic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("epics.id", ondelete="SET NULL"), nullable=True
    )
    host: Mapped[str] = mapped_column(String(64), default="")
    client: Mapped[str] = mapped_column(String(64), default="")
    session_id: Mapped[str] = mapped_column(String(128), default="")
    turn_id: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    retention_class: Mapped[str] = mapped_column(String(32), default="durable")
    importance: Mapped[str] = mapped_column(String(16), default="normal")
