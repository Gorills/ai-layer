"""incremental content identity fields

Revision ID: 0004_incremental_identity
Revises: 0003_session_evidence_defaults
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_incremental_identity"
down_revision = "0003_session_evidence_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_files",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "project_files",
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_files",
        sa.Column("ctime_ns", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_files",
        sa.Column("indexed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "project_files",
        sa.Column("scanner_schema", sa.Integer(), nullable=False, server_default="1"),
    )
    # Existing v0.1 `sha256` is a semantic-text hash, not guaranteed to equal the new raw-content
    # identity. It is only a non-null compatibility seed: mtime/ctime=0 and scanner_schema=1 force
    # the first v0.2 refresh to verify/reparse every legacy row before publishing v2 state.
    op.execute("UPDATE project_files SET content_sha256 = sha256 WHERE content_sha256 IS NULL")
    op.alter_column("project_files", "content_sha256", nullable=False)
    op.alter_column("project_files", "mtime_ns", server_default=None)
    op.alter_column("project_files", "ctime_ns", server_default=None)
    op.alter_column("project_files", "indexed", server_default=None)
    op.alter_column("project_files", "scanner_schema", server_default=None)


def downgrade() -> None:
    op.drop_column("project_files", "scanner_schema")
    op.drop_column("project_files", "indexed")
    op.drop_column("project_files", "ctime_ns")
    op.drop_column("project_files", "mtime_ns")
    op.drop_column("project_files", "content_sha256")
