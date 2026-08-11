"""task execution state machine

Revision ID: 0005_task_execution
Revises: 0004_incremental_identity
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_task_execution"
down_revision = "0004_incremental_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_round", sa.Integer(), nullable=False),
        sa.Column("fix_round", sa.Integer(), nullable=False),
        sa.Column("baseline_digest", sa.String(length=64), nullable=False),
        sa.Column("baseline_files", sa.Integer(), nullable=False),
        sa.Column("final_changes", sa.JSON(), nullable=False),
        sa.Column("completion_summary", sa.Text(), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=False),
        sa.Column("handoff_session_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "sequence", name="uq_task_project_sequence"),
    )
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "status"], unique=False)
    op.create_table(
        "task_stages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("review_round", sa.Integer(), nullable=False),
        sa.Column("fix_round", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("repository_digest_before", sa.String(length=64), nullable=False),
        sa.Column("repository_digest_after", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "ordinal", name="uq_task_stage_ordinal"),
    )
    op.create_index(
        "ix_task_stages_task_status", "task_stages", ["task_id", "status"], unique=False
    )
    op.create_table(
        "review_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("required_fix", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["stage_id"], ["task_stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_findings_task_status", "review_findings", ["task_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_review_findings_task_status", table_name="review_findings")
    op.drop_table("review_findings")
    op.drop_index("ix_task_stages_task_status", table_name="task_stages")
    op.drop_table("task_stages")
    op.drop_index("ix_tasks_project_status", table_name="tasks")
    op.drop_table("tasks")
