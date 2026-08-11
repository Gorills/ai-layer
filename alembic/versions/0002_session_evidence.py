"""session evidence fields

Revision ID: 0002_session_evidence
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_session_evidence"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _session_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {str(column["name"]) for column in inspector.get_columns("sessions")}


def upgrade() -> None:
    columns = _session_columns()
    if "verified_facts" not in columns:
        op.add_column(
            "sessions",
            sa.Column(
                "verified_facts", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
            ),
        )
        op.alter_column("sessions", "verified_facts", server_default=None)
    if "notable_findings" not in columns:
        op.add_column(
            "sessions",
            sa.Column(
                "notable_findings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
            ),
        )
        op.alter_column("sessions", "notable_findings", server_default=None)


def downgrade() -> None:
    columns = _session_columns()
    if "notable_findings" in columns:
        op.drop_column("sessions", "notable_findings")
    if "verified_facts" in columns:
        op.drop_column("sessions", "verified_facts")
