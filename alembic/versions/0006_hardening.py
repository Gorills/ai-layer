"""transactional/review/query hardening

Revision ID: 0006_hardening
Revises: 0005_task_execution
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_hardening"
down_revision = "0005_task_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_findings",
        sa.Column("verification_evidence", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "review_findings",
        sa.Column(
            "verification_history",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "review_findings",
        sa.Column("verified_by_stage_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_findings_verified_by_stage",
        "review_findings",
        "task_stages",
        ["verified_by_stage_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_decisions_project", "decisions", ["project_id"], unique=False)
    op.create_index(
        "ix_sessions_project_created", "sessions", ["project_id", "created_at"], unique=False
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decisions_embedding_hnsw "
        "ON decisions USING hnsw (embedding vector_cosine_ops)"
    )
    op.alter_column("review_findings", "verification_evidence", server_default=None)
    op.alter_column("review_findings", "verification_history", server_default=None)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_decisions_embedding_hnsw")
    op.drop_index("ix_sessions_project_created", table_name="sessions")
    op.drop_index("ix_decisions_project", table_name="decisions")
    op.drop_constraint(
        "fk_review_findings_verified_by_stage",
        "review_findings",
        type_="foreignkey",
    )
    op.drop_column("review_findings", "verified_by_stage_id")
    op.drop_column("review_findings", "verification_history")
    op.drop_column("review_findings", "verification_evidence")
