"""Add durable Epic specification, audit and scheduling state.

Revision ID: 0014_epics_v1
Revises: 0013_dirty_task_baselines
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_epics_v1"
down_revision = "0013_dirty_task_baselines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "epics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_spec_version", sa.Integer(), nullable=False),
        sa.Column("approved_spec_version", sa.Integer(), nullable=True),
        sa.Column("execution_spec_version", sa.Integer(), nullable=True),
        sa.Column("phase0_task_id", sa.Uuid(), nullable=True),
        sa.Column("drift_task_id", sa.Uuid(), nullable=True),
        sa.Column("phase0_summary", sa.Text(), nullable=False),
        sa.Column("phase0_corrections", sa.JSON(), nullable=False),
        sa.Column("decision_required", sa.JSON(), nullable=False),
        sa.Column("execution_digest", sa.String(length=64), nullable=False),
        sa.Column("execution_files", sa.Integer(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','approved','phase0','planning','running','final_review','blocked','completed','archived','cancelled')",
            name="ck_epics_status",
        ),
        sa.CheckConstraint("current_spec_version >= 1", name="ck_epics_current_spec_version"),
        sa.CheckConstraint("plan_version >= 0", name="ck_epics_plan_version"),
        sa.ForeignKeyConstraint(["drift_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["phase0_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "sequence", name="uq_epics_project_sequence"),
    )
    op.create_index("ix_epics_project_status", "epics", ["project_id", "status"], unique=False)

    op.create_table(
        "epic_spec_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("epic_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("epic_id", "version", name="uq_epic_spec_version"),
    )
    op.create_index(
        "ix_epic_spec_versions_epic",
        "epic_spec_versions",
        ["epic_id", "version"],
        unique=False,
    )

    op.create_table(
        "epic_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("epic_id", sa.Uuid(), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("auditor_id", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_epic_audits_epic_created", "epic_audits", ["epic_id", "created_at"], unique=False
    )

    op.create_table(
        "epic_plan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("epic_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('phase0','work','final')", name="ck_epic_plan_items_kind"),
        sa.CheckConstraint(
            "status IN ('pending','active','completed','blocked','cancelled')",
            name="ck_epic_plan_items_status",
        ),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("epic_id", "ordinal", name="uq_epic_plan_item_ordinal"),
    )
    op.create_index(
        "ix_epic_plan_items_epic_status",
        "epic_plan_items",
        ["epic_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_epic_plan_items_epic_status", table_name="epic_plan_items")
    op.drop_table("epic_plan_items")
    op.drop_index("ix_epic_audits_epic_created", table_name="epic_audits")
    op.drop_table("epic_audits")
    op.drop_index("ix_epic_spec_versions_epic", table_name="epic_spec_versions")
    op.drop_table("epic_spec_versions")
    op.drop_index("ix_epics_project_status", table_name="epics")
    op.drop_table("epics")
