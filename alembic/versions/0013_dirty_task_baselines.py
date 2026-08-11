"""Allow managed tasks to start from a captured dirty worktree baseline.

Revision ID: 0013_dirty_task_baselines
Revises: 0012_architecture_hardening
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_dirty_task_baselines"
down_revision = "0012_architecture_hardening"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(item.get("name")) for item in inspector.get_columns(table)}


def upgrade() -> None:
    if "preexisting_changes" not in _columns("tasks"):
        op.add_column(
            "tasks",
            sa.Column(
                "preexisting_changes",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
    op.alter_column("tasks", "preexisting_changes", server_default=None)


def downgrade() -> None:
    if "preexisting_changes" in _columns("tasks"):
        op.drop_column("tasks", "preexisting_changes")
