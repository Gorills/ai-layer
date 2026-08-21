from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ai_layer.db.base import Base
from ai_layer.db.models import utcnow

PUBLIC_ACTION_KINDS = ("native_engineering", "run_worker", "human_decision", "done")
PUBLIC_WORKER_KINDS = ("change", "independent_check", "correction", "discovery")


class WorkActionState(Base):
    """Current server-owned public action for one durable Work outcome."""

    __tablename__ = "work_action_states"
    __table_args__ = (
        Index("ix_work_action_states_project", "project_id", "updated_at"),
        Index("ix_work_action_states_task", "task_id"),
        Index("ix_work_action_states_stage", "stage_id"),
        CheckConstraint("state_version >= 1", name="ck_work_action_states_version"),
        CheckConstraint(
            "action_kind IN ('native_engineering','run_worker','human_decision','done')",
            name="ck_work_action_states_kind",
        ),
        CheckConstraint(
            "worker_kind IS NULL OR worker_kind IN ('change','independent_check','correction','discovery')",
            name="ck_work_action_states_worker_kind",
        ),
    )

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_stages.id", ondelete="SET NULL"), nullable=True
    )
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    worker_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    worker_id: Mapped[str] = mapped_column(String(128), default="")
    action_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    instruction: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkActionSubmission(Base):
    """Consumed action token + canonical report fingerprint for durable idempotent replay."""

    __tablename__ = "work_action_submissions"
    __table_args__ = (
        Index("ix_work_action_submissions_work", "work_id", "created_at"),
        CheckConstraint("state_version >= 1", name="ck_work_action_submissions_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
    )
    action_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    report_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
