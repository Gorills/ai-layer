"""task provenance and unmanaged-change adoption

Revision ID: 0007_task_adoption
Revises: 0006_hardening
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_task_adoption"
down_revision = "0006_hardening"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(item.get("name")) for item in inspector.get_columns(table)}


def upgrade() -> None:
    # This migration is intentionally tolerant of a historical unversioned create_all schema.
    # Such a schema may already contain current ORM columns before Alembic owns the database.
    columns = _columns("tasks")
    if "execution_origin" not in columns:
        op.add_column(
            "tasks",
            sa.Column(
                "execution_origin", sa.String(length=32), nullable=False, server_default="managed"
            ),
        )
    if "adopted_changes" not in columns:
        op.add_column(
            "tasks",
            sa.Column(
                "adopted_changes", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")
            ),
        )
    # 0006 introduced this auxiliary index, but historical create_all databases could have its
    # columns without this raw PostgreSQL-only index. Reconcile it idempotently while upgrading.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_decisions_embedding_hnsw "
            "ON decisions USING hnsw (embedding vector_cosine_ops)"
        )
    op.alter_column("tasks", "execution_origin", server_default=None)
    op.alter_column("tasks", "adopted_changes", server_default=None)


def downgrade() -> None:
    columns = _columns("tasks")
    if "adopted_changes" in columns:
        op.drop_column("tasks", "adopted_changes")
    if "execution_origin" in columns:
        op.drop_column("tasks", "execution_origin")
