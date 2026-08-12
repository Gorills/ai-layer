"""Add metadata-only Project Map navigation index.

Revision ID: 0015_project_navigation
Revises: 0014_epics_v1
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

revision = "0015_project_navigation"
down_revision = "0014_epics_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_navigation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("imports", sa.JSON(), nullable=False),
        sa.Column("risk_flags", sa.JSON(), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("navigation_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("scanner_schema", sa.Integer(), nullable=False),
        sa.Column("embedding", VECTOR(384), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "path", name="uq_project_navigation_path"),
    )
    op.create_index("ix_project_navigation_project", "project_navigation", ["project_id"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_navigation_embedding_hnsw "
        "ON project_navigation USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_project_navigation_embedding_hnsw")
    op.drop_index("ix_project_navigation_project", table_name="project_navigation")
    op.drop_table("project_navigation")
