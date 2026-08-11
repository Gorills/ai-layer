from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ai_layer.db.models import Base, utcnow


class Epic(Base):
    __tablename__ = "epics"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_epics_project_sequence"),
        Index("ix_epics_project_status", "project_id", "status"),
        CheckConstraint(
            "status IN ('draft','approved','phase0','planning','running','final_review','blocked','completed','archived','cancelled')",
            name="ck_epics_status",
        ),
        CheckConstraint("current_spec_version >= 1", name="ck_epics_current_spec_version"),
        CheckConstraint("plan_version >= 0", name="ck_epics_plan_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    current_spec_version: Mapped[int] = mapped_column(Integer, default=1)
    approved_spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase0_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    drift_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    phase0_summary: Mapped[str] = mapped_column(Text, default="")
    phase0_corrections: Mapped[list] = mapped_column(JSON, default=list)
    decision_required: Mapped[list] = mapped_column(JSON, default=list)
    execution_digest: Mapped[str] = mapped_column(String(64), default="")
    execution_files: Mapped[int] = mapped_column(Integer, default=0)
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EpicSpecVersion(Base):
    __tablename__ = "epic_spec_versions"
    __table_args__ = (
        UniqueConstraint("epic_id", "version", name="uq_epic_spec_version"),
        Index("ix_epic_spec_versions_epic", "epic_id", "version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    epic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("epics.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="draft")
    change_summary: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EpicAudit(Base):
    __tablename__ = "epic_audits"
    __table_args__ = (Index("ix_epic_audits_epic_created", "epic_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    epic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("epics.id", ondelete="CASCADE"))
    spec_version: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(64), default="independent")
    auditor_id: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EpicPlanItem(Base):
    __tablename__ = "epic_plan_items"
    __table_args__ = (
        UniqueConstraint("epic_id", "ordinal", name="uq_epic_plan_item_ordinal"),
        Index("ix_epic_plan_items_epic_status", "epic_id", "status"),
        CheckConstraint("kind IN ('phase0','work','final')", name="ck_epic_plan_items_kind"),
        CheckConstraint(
            "status IN ('pending','active','completed','blocked','cancelled')",
            name="ck_epic_plan_items_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    epic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("epics.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    constraints: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    spec_version: Mapped[int] = mapped_column(Integer)
    plan_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
