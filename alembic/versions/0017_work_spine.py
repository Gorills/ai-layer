"""Add durable ordinary-work and agent-run observability spine.

Revision ID: 0017_work_spine
Revises: 0016_project_map_semantics
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_work_spine"
down_revision = "0016_project_map_semantics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False),
        sa.Column("reviewed_paths", sa.JSON(), nullable=False),
        sa.Column("changed_paths", sa.JSON(), nullable=False),
        sa.Column("repository_delta", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("map_disposition", sa.JSON(), nullable=False),
        sa.Column("observability_coverage", sa.String(length=32), nullable=False),
        sa.Column("assurance", sa.String(length=32), nullable=False),
        sa.Column("linked_task_id", sa.Uuid(), nullable=True),
        sa.Column("linked_epic_id", sa.Uuid(), nullable=True),
        sa.Column("legacy_session_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_milestone_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('change','diagnose','review','research','planning','ops')",
            name="ck_work_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active','blocked','completed','failed','interrupted','abandoned')",
            name="ck_work_items_status",
        ),
        sa.CheckConstraint(
            "observability_coverage IN ('full_host_hooks','lifecycle_only',"
            "'control_plane_only','inferred_repository_delta','unavailable')",
            name="ck_work_items_observability_coverage",
        ),
        sa.CheckConstraint(
            "assurance IN ('ai_layer_observed','host_reported','agent_reported',"
            "'inferred_unattributed','requested_unverified')",
            name="ck_work_items_assurance",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_epic_id"], ["epics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["legacy_session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "sequence", name="uq_work_items_project_sequence"),
    )
    op.create_index(
        "ix_work_items_project_status_updated",
        "work_items",
        ["project_id", "status", "updated_at"],
    )
    op.add_column(
        "project_navigation_semantics",
        sa.Column("source_work_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_navigation_semantics_source_work",
        "project_navigation_semantics",
        "work_items",
        ["source_work_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_project_navigation_semantics_source_work",
        "project_navigation_semantics",
        ["source_work_id"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("parent_run_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("host", sa.String(length=64), nullable=False),
        sa.Column("client", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("turn_id", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("last_meaningful_action", sa.Text(), nullable=False),
        sa.Column("observability_coverage", sa.String(length=32), nullable=False),
        sa.Column("assurance", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('root','subagent')", name="ck_agent_runs_role"),
        sa.CheckConstraint(
            "status IN ('active','completed','failed','interrupted','abandoned')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "observability_coverage IN ('full_host_hooks','lifecycle_only',"
            "'control_plane_only','inferred_repository_delta','unavailable')",
            name="ck_agent_runs_observability_coverage",
        ),
        sa.CheckConstraint(
            "assurance IN ('ai_layer_observed','host_reported','agent_reported',"
            "'inferred_unattributed','requested_unverified')",
            name="ck_agent_runs_assurance",
        ),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_runs_work_status_heartbeat",
        "agent_runs",
        ["work_id", "status", "heartbeat_at"],
    )

    op.create_table(
        "runtime_event_context",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("epic_id", sa.Uuid(), nullable=True),
        sa.Column("host", sa.String(length=64), nullable=False),
        sa.Column("client", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("turn_id", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("retention_class", sa.String(length=32), nullable=False),
        sa.Column("importance", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["runtime_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_runtime_event_context_work",
        "runtime_event_context",
        ["work_id", "event_id"],
    )
    op.create_index(
        "ix_runtime_event_context_run",
        "runtime_event_context",
        ["run_id", "event_id"],
    )
    op.create_index(
        "ix_runtime_event_context_task",
        "runtime_event_context",
        ["task_id", "event_id"],
    )
    op.create_index(
        "ix_runtime_event_context_epic",
        "runtime_event_context",
        ["epic_id", "event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_event_context_epic", table_name="runtime_event_context")
    op.drop_index("ix_runtime_event_context_task", table_name="runtime_event_context")
    op.drop_index("ix_runtime_event_context_run", table_name="runtime_event_context")
    op.drop_index("ix_runtime_event_context_work", table_name="runtime_event_context")
    op.drop_table("runtime_event_context")
    op.drop_index("ix_agent_runs_work_status_heartbeat", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(
        "ix_project_navigation_semantics_source_work",
        table_name="project_navigation_semantics",
    )
    op.drop_constraint(
        "fk_project_navigation_semantics_source_work",
        "project_navigation_semantics",
        type_="foreignkey",
    )
    op.drop_column("project_navigation_semantics", "source_work_id")
    op.drop_index("ix_work_items_project_status_updated", table_name="work_items")
    op.drop_table("work_items")
