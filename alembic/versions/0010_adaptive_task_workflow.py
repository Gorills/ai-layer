"""Add adaptive task workflow and cost-aware delegation metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0010_adaptive_task_workflow"
down_revision = "0009_project_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing in-flight/completed tasks retain workflow v1 semantics. New runtime-created tasks
    # explicitly write workflow_version=2, so upgrading cannot silently change an active task.
    op.add_column(
        "tasks", sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "tasks",
        sa.Column(
            "workflow_profile",
            sa.String(length=32),
            nullable=False,
            server_default="legacy_standard",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "tasks",
        sa.Column("risk_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "tasks",
        sa.Column("cost_policy", sa.String(length=16), nullable=False, server_default="economy"),
    )
    op.add_column(
        "tasks",
        sa.Column("discovery_result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.add_column(
        "task_stages",
        sa.Column("agent_tier", sa.String(length=16), nullable=False, server_default=""),
    )
    op.add_column(
        "task_stages",
        sa.Column("agent_profile", sa.String(length=96), nullable=False, server_default=""),
    )
    op.add_column(
        "task_stages",
        sa.Column("agent_model", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "task_stages",
        sa.Column("agent_policy_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "task_stages",
        sa.Column("readonly_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "task_stages",
        sa.Column("result_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    for column in (
        "result_data",
        "readonly_required",
        "agent_policy_reason",
        "agent_model",
        "agent_profile",
        "agent_tier",
    ):
        op.drop_column("task_stages", column)
    for column in (
        "discovery_result",
        "cost_policy",
        "risk_reasons",
        "risk_level",
        "workflow_profile",
        "workflow_version",
    ):
        op.drop_column("tasks", column)
