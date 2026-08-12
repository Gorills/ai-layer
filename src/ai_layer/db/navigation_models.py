from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ai_layer.db.base import Base
from ai_layer.db.models import utcnow


class ProjectNavigation(Base):
    """Searchable repository breadcrumbs without persisted source bodies."""

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
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
