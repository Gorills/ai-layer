from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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

from ai_layer.db.base import Base
from ai_layer.db.models import utcnow

TASK_WORK_ROLES = ("outcome", "epic_control")
BACKFILL_STATUSES = ("resolved", "missing", "ambiguous", "unresolved", "ignored_control")


class TaskWorkRelation(Base):
    """Canonical Task -> Work ownership; historical Tasks may share one Work over time."""

    __tablename__ = "task_work_relations"
    __table_args__ = (
        Index("ix_task_work_relations_work", "work_id"),
        CheckConstraint(
            "role IN ('outcome','epic_control')",
            name="ck_task_work_relations_role",
        ),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(24), default="outcome")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EpicWorkRelation(Base):
    """Canonical Epic -> root Work relation."""

    __tablename__ = "epic_work_relations"
    __table_args__ = (
        UniqueConstraint("root_work_id", name="uq_epic_work_relations_root_work"),
        Index("ix_epic_work_relations_root", "root_work_id"),
    )
    epic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("epics.id", ondelete="CASCADE"), primary_key=True
    )
    root_work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkHierarchy(Base):
    """Canonical parent/root relation. Root Work points root_work_id at itself."""

    __tablename__ = "work_hierarchy"
    __table_args__ = (
        Index("ix_work_hierarchy_parent", "parent_work_id"),
        Index("ix_work_hierarchy_root", "root_work_id"),
        CheckConstraint(
            "parent_work_id IS NULL OR parent_work_id <> work_id",
            name="ck_work_hierarchy_parent_not_self",
        ),
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), primary_key=True
    )
    parent_work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True
    )
    root_work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EpicPlanWorkRelation(Base):
    """Canonical user-visible child Work for one Epic implementation plan item."""

    __tablename__ = "epic_plan_work_relations"
    __table_args__ = (
        UniqueConstraint("work_id", name="uq_epic_plan_work_relations_work"),
        Index("ix_epic_plan_work_relations_work", "work_id"),
    )
    plan_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("epic_plan_items.id", ondelete="CASCADE"), primary_key=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkRelationBackfillAudit(Base):
    """Durable classification of legacy weak links that Phase 2 may or may not resolve."""

    __tablename__ = "work_relation_backfill_audit"
    __table_args__ = (
        Index("ix_work_relation_backfill_owner", "owner_type", "owner_id"),
        CheckConstraint(
            "status IN ('resolved','missing','ambiguous','unresolved','ignored_control')",
            name="ck_work_relation_backfill_status",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
