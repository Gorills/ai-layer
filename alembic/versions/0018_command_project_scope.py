"""Scope command receipts to project identity.

Revision ID: 0018_command_project_scope
Revises: 0017_work_spine
"""

from alembic import op

revision = "0018_command_project_scope"
down_revision = "0017_work_spine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_command_receipts_command_id", "command_receipts", type_="unique")
    op.create_unique_constraint(
        "uq_command_receipts_project_command",
        "command_receipts",
        ["project_id", "command_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_command_receipts_project_command", "command_receipts", type_="unique")
    op.create_unique_constraint(
        "uq_command_receipts_command_id",
        "command_receipts",
        ["command_id"],
    )
