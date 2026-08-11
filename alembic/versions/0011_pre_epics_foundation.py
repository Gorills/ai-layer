"""Pre-Epics foundation: verification evidence, model assurance, structured events.

Revision ID: 0011_pre_epics_foundation
Revises: 0010_adaptive_task_workflow
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_pre_epics_foundation"
down_revision = "0010_adaptive_task_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "complexity_level", sa.String(length=16), nullable=False, server_default="normal"
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "uncertainty_level", sa.String(length=16), nullable=False, server_default="normal"
        ),
    )
    op.add_column(
        "task_stages",
        sa.Column("actual_model", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "task_stages", sa.Column("worker_heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "task_stages",
        sa.Column("worker_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "task_stages",
        sa.Column(
            "model_assurance",
            sa.String(length=32),
            nullable=False,
            server_default="requested_unverified",
        ),
    )
    op.add_column(
        "task_stages",
        sa.Column("telemetry", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "review_findings",
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.create_table(
        "verification_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("stage_id", sa.Uuid(), nullable=True),
        sa.Column("assurance", sa.String(length=32), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("cwd", sa.Text(), nullable=False),
        sa.Column("environment", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("timed_out", sa.Boolean(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_id"], ["task_stages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_verification_runs_project_created",
        "verification_runs",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_verification_runs_stage", "verification_runs", ["stage_id"], unique=False)

    op.create_table(
        "runtime_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runtime_events_project_created",
        "runtime_events",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_events_aggregate",
        "runtime_events",
        ["aggregate_type", "aggregate_id", "created_at"],
        unique=False,
    )

    op.alter_column("tasks", "complexity_level", server_default=None)
    op.alter_column("tasks", "uncertainty_level", server_default=None)
    op.alter_column("task_stages", "actual_model", server_default=None)
    op.alter_column("task_stages", "model_assurance", server_default=None)
    op.alter_column("task_stages", "telemetry", server_default=None)
    op.alter_column("review_findings", "provenance", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_runtime_events_aggregate", table_name="runtime_events")
    op.drop_index("ix_runtime_events_project_created", table_name="runtime_events")
    op.drop_table("runtime_events")
    op.drop_index("ix_verification_runs_stage", table_name="verification_runs")
    op.drop_index("ix_verification_runs_project_created", table_name="verification_runs")
    op.drop_table("verification_runs")
    op.drop_column("review_findings", "provenance")
    op.drop_column("task_stages", "telemetry")
    op.drop_column("task_stages", "model_assurance")
    op.drop_column("task_stages", "actual_model")
    op.drop_column("task_stages", "worker_lease_expires_at")
    op.drop_column("task_stages", "worker_heartbeat_at")
    op.drop_column("tasks", "uncertainty_level")
    op.drop_column("tasks", "complexity_level")
