"""Store deterministic structured project intelligence for adaptive skill routing."""

from alembic import op
import sqlalchemy as sa

revision = "0009_project_intelligence"
down_revision = "0008_workflow_navigation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("project_intelligence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("projects", "project_intelligence")
