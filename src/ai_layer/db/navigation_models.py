from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ai_layer.db.base import Base
from ai_layer.db.models import utcnow


class ProjectNavigation(Base):
    """Scanner-owned searchable repository breadcrumbs without persisted source bodies."""

    __tablename__ = "project_navigation"
    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_project_navigation_path"),
        Index("ix_project_navigation_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(Text)
    imports: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    symbols: Mapped[list] = mapped_column(JSON, default=list)
    navigation_text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    scanner_schema: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(384), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectNavigationSemantic(Base):
    """Agent-authored semantic navigation layered over scanner-owned ProjectNavigation rows.

    This table intentionally survives source refreshes. Freshness is derived by comparing the
    evidence hash stored here with the current scanner-owned ProjectNavigation.content_sha256.
    Source bodies are never persisted.
    """

    __tablename__ = "project_navigation_semantics"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "path", name="uq_project_navigation_semantic_path"
        ),
        Index("ix_project_navigation_semantic_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text, default="")
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    domain_terms: Mapped[list] = mapped_column(JSON, default=list)
    important_symbols: Mapped[list] = mapped_column(JSON, default=list)
    related_files: Mapped[list] = mapped_column(JSON, default=list)
    related_tests: Mapped[list] = mapped_column(JSON, default=list)
    navigation_hints: Mapped[list] = mapped_column(JSON, default=list)
    semantic_text: Mapped[str] = mapped_column(Text, default="")
    content_sha256: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(32), default="agent")
    source_ref: Mapped[str] = mapped_column(String(128), default="")
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
