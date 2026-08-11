"""Durable workflow snapshots, DB invariants, event/security/idempotency foundation.

Revision ID: 0012_architecture_hardening
Revises: 0011_pre_epics_foundation
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_architecture_hardening"
down_revision = "0011_pre_epics_foundation"
branch_labels = None
depends_on = None


def _assert_no_duplicate_open_tasks() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT project_id, COUNT(*) AS count
            FROM tasks
            WHERE status IN ('active', 'blocked')
            GROUP BY project_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if rows:
        raise RuntimeError(
            "Cannot enforce one-open-task invariant: duplicate active/blocked tasks exist for "
            + ", ".join(str(row[0]) for row in rows[:10])
        )


def _assert_no_duplicate_active_stages() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT task_id, COUNT(*) AS count
            FROM task_stages
            WHERE status = 'active'
            GROUP BY task_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if rows:
        raise RuntimeError(
            "Cannot enforce one-active-stage invariant: duplicate active stages exist for "
            + ", ".join(str(row[0]) for row in rows[:10])
        )


def upgrade() -> None:
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name="ck_repository_snapshot_schema"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repository_snapshots_project_created",
        "repository_snapshots",
        ["project_id", "created_at"],
        unique=False,
    )

    op.add_column("tasks", sa.Column("baseline_snapshot_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_foreign_key(
        "fk_tasks_baseline_snapshot_id_repository_snapshots",
        "tasks",
        "repository_snapshots",
        ["baseline_snapshot_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_tasks_status",
        "tasks",
        "status IN ('active', 'blocked', 'completed', 'cancelled')",
    )
    op.create_check_constraint("ck_tasks_version", "tasks", "version >= 1")
    _assert_no_duplicate_open_tasks()
    op.create_index(
        "uq_tasks_one_open_per_project",
        "tasks",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'blocked')"),
        sqlite_where=sa.text("status IN ('active', 'blocked')"),
    )

    op.add_column("task_stages", sa.Column("start_snapshot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_task_stages_start_snapshot_id_repository_snapshots",
        "task_stages",
        "repository_snapshots",
        ["start_snapshot_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        "ck_task_stages_kind",
        "task_stages",
        "kind IN ('discovery', 'implement', 'review', 'fix')",
    )
    op.create_check_constraint(
        "ck_task_stages_status",
        "task_stages",
        "status IN ('active', 'completed', 'blocked', 'invalid', 'cancelled')",
    )
    _assert_no_duplicate_active_stages()
    op.create_index(
        "uq_task_stages_one_active_per_task",
        "task_stages",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.add_column(
        "runtime_events",
        sa.Column("correlation_id", sa.String(length=64), nullable=False, server_default="legacy"),
    )
    op.add_column("runtime_events", sa.Column("causation_id", sa.String(length=64), nullable=True))
    op.add_column(
        "runtime_events",
        sa.Column(
            "actor_id", sa.String(length=128), nullable=False, server_default="system:legacy"
        ),
    )
    op.add_column(
        "runtime_events",
        sa.Column("actor_kind", sa.String(length=32), nullable=False, server_default="system"),
    )
    op.add_column(
        "runtime_events",
        sa.Column("interface", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    op.add_column("runtime_events", sa.Column("command_id", sa.String(length=128), nullable=True))
    op.add_column(
        "runtime_events",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "event_consumer_checkpoints",
        sa.Column("consumer_name", sa.String(length=128), nullable=False),
        sa.Column("last_event_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_event_id"], ["runtime_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("consumer_name"),
    )
    op.create_table(
        "command_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("command_name", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed')", name="ck_command_receipts_status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_command_receipts_command_id"),
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("requested_by_kind", sa.String(length=32), nullable=False),
        sa.Column("required_capability", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'resolved', 'cancelled')", name="ck_approval_requests_status"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_requests_project_status",
        "approval_requests",
        ["project_id", "status"],
        unique=False,
    )

    op.alter_column("tasks", "version", server_default=None)
    for column in ("correlation_id", "actor_id", "actor_kind", "interface", "schema_version"):
        op.alter_column("runtime_events", column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_approval_requests_project_status", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_table("command_receipts")
    op.drop_table("event_consumer_checkpoints")
    for column in (
        "schema_version",
        "command_id",
        "interface",
        "actor_kind",
        "actor_id",
        "causation_id",
        "correlation_id",
    ):
        op.drop_column("runtime_events", column)

    op.drop_index("uq_task_stages_one_active_per_task", table_name="task_stages")
    op.drop_constraint("ck_task_stages_status", "task_stages", type_="check")
    op.drop_constraint("ck_task_stages_kind", "task_stages", type_="check")
    op.drop_constraint(
        "fk_task_stages_start_snapshot_id_repository_snapshots",
        "task_stages",
        type_="foreignkey",
    )
    op.drop_column("task_stages", "start_snapshot_id")

    op.drop_index("uq_tasks_one_open_per_project", table_name="tasks")
    op.drop_constraint("ck_tasks_version", "tasks", type_="check")
    op.drop_constraint("ck_tasks_status", "tasks", type_="check")
    op.drop_constraint(
        "fk_tasks_baseline_snapshot_id_repository_snapshots", "tasks", type_="foreignkey"
    )
    op.drop_column("tasks", "version")
    op.drop_column("tasks", "baseline_snapshot_id")

    op.drop_index("ix_repository_snapshots_project_created", table_name="repository_snapshots")
    op.drop_table("repository_snapshots")
