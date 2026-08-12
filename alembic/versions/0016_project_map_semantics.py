"""Add agent-authored semantic Project Map enrichment.

Revision ID: 0016_project_map_semantics
Revises: 0015_project_navigation
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

revision = "0016_project_map_semantics"
down_revision = "0015_project_navigation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_navigation_semantics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("responsibilities", sa.JSON(), nullable=False),
        sa.Column("domain_terms", sa.JSON(), nullable=False),
        sa.Column("important_symbols", sa.JSON(), nullable=False),
        sa.Column("related_files", sa.JSON(), nullable=False),
        sa.Column("related_tests", sa.JSON(), nullable=False),
        sa.Column("navigation_hints", sa.JSON(), nullable=False),
        sa.Column("semantic_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("source_task_id", sa.Uuid(), nullable=True),
        sa.Column("embedding", VECTOR(384), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "path", name="uq_project_navigation_semantic_path"),
    )
    op.create_index(
        "ix_project_navigation_semantic_project",
        "project_navigation_semantics",
        ["project_id"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_navigation_semantic_embedding_hnsw "
        "ON project_navigation_semantics USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_project_navigation_semantic_embedding_hnsw")
    op.drop_index(
        "ix_project_navigation_semantic_project",
        table_name="project_navigation_semantics",
    )
    op.drop_table("project_navigation_semantics")
