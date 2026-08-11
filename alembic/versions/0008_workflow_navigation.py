"""workflow navigation and explicit stage delegation

Revision ID: 0008_workflow_navigation
Revises: 0007_task_adoption
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_workflow_navigation"
down_revision = "0007_task_adoption"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(item.get("name")) for item in inspector.get_columns(table)}


def upgrade() -> None:
    columns = _columns("task_stages")
    # Existing active stages predate explicit delegation and therefore remain legacy-compatible.
    # Newly created stages are marked delegation_required=True by the ORM/service layer.
    if "delegation_required" not in columns:
        op.add_column(
            "task_stages",
            sa.Column("delegation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "delegated_at" not in columns:
        op.add_column("task_stages", sa.Column("delegated_at", sa.DateTime(timezone=True), nullable=True))
    if "external_actions" not in columns:
        op.add_column(
            "task_stages",
            sa.Column("external_actions", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        )
    op.alter_column("task_stages", "delegation_required", server_default=None)
    op.alter_column("task_stages", "external_actions", server_default=None)


def downgrade() -> None:
    columns = _columns("task_stages")
    if "external_actions" in columns:
        op.drop_column("task_stages", "external_actions")
    if "delegated_at" in columns:
        op.drop_column("task_stages", "delegated_at")
    if "delegation_required" in columns:
        op.drop_column("task_stages", "delegation_required")
