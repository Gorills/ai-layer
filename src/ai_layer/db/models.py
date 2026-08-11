from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    root_path: Mapped[str] = mapped_column(Text, unique=True)
    languages: Mapped[dict] = mapped_column(JSON, default=dict)
    dependencies: Mapped[dict] = mapped_column(JSON, default=dict)
    architecture_summary: Mapped[str] = mapped_column(Text, default="")
    project_intelligence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectFile(Base):
    __tablename__ = "project_files"
    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_project_file_path"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(Text)
    imports: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer)
    mtime_ns: Mapped[int] = mapped_column(BigInteger, default=0)
    ctime_ns: Mapped[int] = mapped_column(BigInteger, default=0)
    indexed: Mapped[bool] = mapped_column(Boolean, default=True)
    scanner_schema: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Knowledge(Base):
    __tablename__ = "knowledge"
    __table_args__ = (Index("ix_knowledge_project_kind", "project_id", "kind"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_project", "project_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_project_created", "project_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    goal: Mapped[str] = mapped_column(Text)
    completed_actions: Mapped[list] = mapped_column(JSON, default=list)
    current_state: Mapped[str] = mapped_column(Text)
    next_steps: Mapped[list] = mapped_column(JSON, default=list)
    important_decisions: Mapped[list] = mapped_column(JSON, default=list)
    verified_facts: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    notable_findings: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RepositorySnapshot(Base):
    """Immutable repository identity metadata used for workflow recovery.

    The payload contains paths, hashes and stat metadata only; repository file contents are never
    copied into PostgreSQL by this store.
    """

    __tablename__ = "repository_snapshots"
    __table_args__ = (
        Index("ix_repository_snapshots_project_created", "project_id", "created_at"),
        CheckConstraint("schema_version >= 1", name="ck_repository_snapshot_schema"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    snapshot_kind: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    digest: Mapped[str] = mapped_column(String(64))
    file_count: Mapped[int] = mapped_column(Integer)
    storage_backend: Mapped[str] = mapped_column(String(32), default="postgresql-json")
    state: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_task_project_sequence"),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index(
            "uq_tasks_one_open_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'blocked')"),
            sqlite_where=text("status IN ('active', 'blocked')"),
        ),
        CheckConstraint(
            "status IN ('active', 'blocked', 'completed', 'cancelled')",
            name="ck_tasks_status",
        ),
        CheckConstraint("version >= 1", name="ck_tasks_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    goal: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    constraints: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active")
    review_round: Mapped[int] = mapped_column(Integer, default=0)
    fix_round: Mapped[int] = mapped_column(Integer, default=0)
    baseline_digest: Mapped[str] = mapped_column(String(64), default="")
    baseline_files: Mapped[int] = mapped_column(Integer, default=0)
    baseline_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", deferrable=True, initially="DEFERRED"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    final_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    completion_summary: Mapped[str] = mapped_column(Text, default="")
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    handoff_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    execution_origin: Mapped[str] = mapped_column(String(32), default="managed")
    adopted_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    preexisting_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    workflow_version: Mapped[int] = mapped_column(Integer, default=2)
    workflow_profile: Mapped[str] = mapped_column(String(32), default="standard")
    risk_level: Mapped[str] = mapped_column(String(16), default="normal")
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)
    complexity_level: Mapped[str] = mapped_column(String(16), default="normal")
    uncertainty_level: Mapped[str] = mapped_column(String(16), default="normal")
    cost_policy: Mapped[str] = mapped_column(String(16), default="economy")
    discovery_result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskStage(Base):
    __tablename__ = "task_stages"
    __table_args__ = (
        UniqueConstraint("task_id", "ordinal", name="uq_task_stage_ordinal"),
        Index("ix_task_stages_task_status", "task_id", "status"),
        Index(
            "uq_task_stages_one_active_per_task",
            "task_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        CheckConstraint(
            "kind IN ('discovery', 'implement', 'review', 'fix')",
            name="ck_task_stages_kind",
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'blocked', 'invalid', 'cancelled')",
            name="ck_task_stages_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="active")
    review_round: Mapped[int] = mapped_column(Integer, default=0)
    fix_round: Mapped[int] = mapped_column(Integer, default=0)
    delegation_required: Mapped[bool] = mapped_column(Boolean, default=True)
    delegated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_id: Mapped[str] = mapped_column(String(128), default="")
    agent_tier: Mapped[str] = mapped_column(String(16), default="")
    agent_profile: Mapped[str] = mapped_column(String(96), default="")
    agent_model: Mapped[str] = mapped_column(String(128), default="")
    agent_policy_reason: Mapped[str] = mapped_column(Text, default="")
    readonly_required: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_model: Mapped[str] = mapped_column(String(128), default="")
    model_assurance: Mapped[str] = mapped_column(String(32), default="requested_unverified")
    telemetry: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(32), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    checks: Mapped[list] = mapped_column(JSON, default=list)
    external_actions: Mapped[list] = mapped_column(JSON, default=list)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    result_data: Mapped[dict] = mapped_column(JSON, default=dict)
    repository_digest_before: Mapped[str] = mapped_column(String(64), default="")
    repository_digest_after: Mapped[str] = mapped_column(String(64), default="")
    start_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", deferrable=True, initially="DEFERRED"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    __table_args__ = (
        Index("ix_verification_runs_project_created", "project_id", "created_at"),
        Index("ix_verification_runs_stage", "stage_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_stages.id", ondelete="CASCADE"), nullable=True
    )
    assurance: Mapped[str] = mapped_column(String(32))
    command: Mapped[list] = mapped_column(JSON, default=list)
    cwd: Mapped[str] = mapped_column(Text)
    environment: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    output_summary: Mapped[str] = mapped_column(Text, default="")
    evidence_ref: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RuntimeEvent(Base):
    __tablename__ = "runtime_events"
    __table_args__ = (
        Index("ix_runtime_events_project_created", "project_id", "created_at"),
        Index("ix_runtime_events_aggregate", "aggregate_type", "aggregate_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(96))
    aggregate_type: Mapped[str] = mapped_column(String(64), default="")
    aggregate_id: Mapped[str] = mapped_column(String(128), default="")
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    causation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(128), default="system:internal")
    actor_kind: Mapped[str] = mapped_column(String(32), default="system")
    interface: Mapped[str] = mapped_column(String(32), default="internal")
    command_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (Index("ix_review_findings_task_status", "task_id", "status"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_stages.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    category: Mapped[str] = mapped_column(String(64), default="code")
    path: Mapped[str] = mapped_column(Text, default="")
    problem: Mapped[str] = mapped_column(Text)
    required_fix: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_evidence: Mapped[str] = mapped_column(Text, default="")
    verification_history: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("'[]'")
    )
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    verified_by_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_stages.id", ondelete="SET NULL"), nullable=True
    )


class ProjectSkill(Base):
    __tablename__ = "project_skills"
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_slug: Mapped[str] = mapped_column(String(128), primary_key=True)
    reason: Mapped[str] = mapped_column(Text)


class EventConsumerCheckpoint(Base):
    __tablename__ = "event_consumer_checkpoints"
    consumer_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runtime_events.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommandReceipt(Base):
    __tablename__ = "command_receipts"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_command_receipts_command_id"),
        CheckConstraint(
            "status IN ('started', 'completed', 'failed')", name="ck_command_receipts_status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    command_id: Mapped[str] = mapped_column(String(128))
    command_name: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="started")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str] = mapped_column(String(128), default="system:internal")
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_project_status", "project_id", "status"),
        CheckConstraint(
            "status IN ('pending', 'resolved', 'cancelled')", name="ck_approval_requests_status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[str] = mapped_column(String(128))
    requested_by_kind: Mapped[str] = mapped_column(String(32), default="user")
    required_capability: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(128), default="")
    decision: Mapped[str] = mapped_column(String(16), default="")
