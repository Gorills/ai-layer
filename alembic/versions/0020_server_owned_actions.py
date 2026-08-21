"""Add durable server-owned facade action state and idempotency journal.

Revision ID: 0020_server_owned_actions
Revises: 0019_canonical_work_relations
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0020_server_owned_actions"
down_revision = "0019_canonical_work_relations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_action_states",
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("stage_id", sa.Uuid(), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("action_kind", sa.String(length=32), nullable=False),
        sa.Column("worker_kind", sa.String(length=32), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=False, server_default=sa.text("''")),
        sa.Column("action_token", sa.String(length=64), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("state_version >= 1", name="ck_work_action_states_version"),
        sa.CheckConstraint(
            "action_kind IN ('native_engineering','run_worker','human_decision','done')",
            name="ck_work_action_states_kind",
        ),
        sa.CheckConstraint(
            "worker_kind IS NULL OR worker_kind IN ('change','independent_check','correction')",
            name="ck_work_action_states_worker_kind",
        ),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["stage_id"], ["task_stages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("work_id"),
        sa.UniqueConstraint("action_token", name="uq_work_action_states_token"),
    )
    op.create_index(
        "ix_work_action_states_project", "work_action_states", ["project_id", "updated_at"]
    )
    op.create_index("ix_work_action_states_task", "work_action_states", ["task_id"])
    op.create_index("ix_work_action_states_stage", "work_action_states", ["stage_id"])

    op.create_table(
        "work_action_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("action_token", sa.String(length=64), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'processing'")),
        sa.Column("response", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("state_version >= 1", name="ck_work_action_submissions_version"),
        sa.CheckConstraint(
            "status IN ('processing','completed')",
            name="ck_work_action_submissions_status",
        ),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_token", name="uq_work_action_submissions_token"),
    )
    op.create_index(
        "ix_work_action_submissions_work",
        "work_action_submissions",
        ["work_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_work_action_submissions_work", table_name="work_action_submissions")
    op.drop_table("work_action_submissions")
    op.drop_index("ix_work_action_states_stage", table_name="work_action_states")
    op.drop_index("ix_work_action_states_task", table_name="work_action_states")
    op.drop_index("ix_work_action_states_project", table_name="work_action_states")
    op.drop_table("work_action_states")
