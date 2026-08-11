"""keep session evidence defaults for backward-compatible MCP writers

Revision ID: 0003_session_evidence_defaults
Revises: 0002_session_evidence
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_session_evidence_defaults"
down_revision = "0002_session_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep server-side defaults permanently. A long-lived IDE may briefly keep an older
    # MCP process alive after an AI Layer upgrade; old writers do not know these columns.
    # The DB must remain write-compatible while the host reconnects.
    op.alter_column(
        "sessions",
        "verified_facts",
        existing_type=sa.JSON(),
        nullable=False,
        server_default=sa.text("'[]'::json"),
    )
    op.alter_column(
        "sessions",
        "notable_findings",
        existing_type=sa.JSON(),
        nullable=False,
        server_default=sa.text("'[]'::json"),
    )


def downgrade() -> None:
    op.alter_column("sessions", "notable_findings", server_default=None)
    op.alter_column("sessions", "verified_facts", server_default=None)
