"""Add canonical Work/Task/Epic relation tables and classify legacy links.

Revision ID: 0019_canonical_work_relations
Revises: 0018_command_project_scope
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0019_canonical_work_relations"
down_revision = "0018_command_project_scope"
branch_labels = None
depends_on = None


def _create_relation_tables() -> None:
    op.create_table(
        "task_work_relations",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'outcome'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "role IN ('outcome','epic_control')",
            name="ck_task_work_relations_role",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_task_work_relations_work", "task_work_relations", ["work_id"])

    op.create_table(
        "epic_work_relations",
        sa.Column("epic_id", sa.Uuid(), nullable=False),
        sa.Column("root_work_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["root_work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("epic_id"),
        sa.UniqueConstraint("root_work_id", name="uq_epic_work_relations_root_work"),
    )
    op.create_index("ix_epic_work_relations_root", "epic_work_relations", ["root_work_id"])

    op.create_table(
        "work_hierarchy",
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("parent_work_id", sa.Uuid(), nullable=True),
        sa.Column("root_work_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "parent_work_id IS NULL OR parent_work_id <> work_id",
            name="ck_work_hierarchy_parent_not_self",
        ),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_work_id"], ["work_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["root_work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("work_id"),
    )
    op.create_index("ix_work_hierarchy_parent", "work_hierarchy", ["parent_work_id"])
    op.create_index("ix_work_hierarchy_root", "work_hierarchy", ["root_work_id"])

    op.create_table(
        "epic_plan_work_relations",
        sa.Column("plan_item_id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["plan_item_id"], ["epic_plan_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_item_id"),
        sa.UniqueConstraint("work_id", name="uq_epic_plan_work_relations_work"),
    )
    op.create_index("ix_epic_plan_work_relations_work", "epic_plan_work_relations", ["work_id"])

    op.create_table(
        "work_relation_backfill_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('resolved','missing','ambiguous','unresolved','ignored_control')",
            name="ck_work_relation_backfill_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_work_relation_backfill_owner",
        "work_relation_backfill_audit",
        ["owner_type", "owner_id"],
    )


def _legacy_control_task_ids(bind: sa.Connection, metadata: sa.MetaData) -> set[object]:
    epics = sa.Table("epics", metadata, autoload_with=bind)
    plan_items = sa.Table("epic_plan_items", metadata, autoload_with=bind)
    ids: set[object] = set()
    for phase0_id, drift_id in bind.execute(
        sa.select(epics.c.phase0_task_id, epics.c.drift_task_id)
    ):
        if phase0_id is not None:
            ids.add(phase0_id)
        if drift_id is not None:
            ids.add(drift_id)
    ids.update(
        row[0]
        for row in bind.execute(
            sa.select(plan_items.c.task_id).where(
                plan_items.c.task_id.is_not(None),
                plan_items.c.kind.in_(("phase0", "final")),
            )
        )
        if row[0] is not None
    )
    return ids


def _backfill_relations() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    tasks = sa.Table("tasks", metadata, autoload_with=bind)
    epics = sa.Table("epics", metadata, autoload_with=bind)
    plan_items = sa.Table("epic_plan_items", metadata, autoload_with=bind)
    work = sa.Table("work_items", metadata, autoload_with=bind)
    task_rel = sa.Table("task_work_relations", metadata, autoload_with=bind)
    plan_rel = sa.Table("epic_plan_work_relations", metadata, autoload_with=bind)
    audit = sa.Table("work_relation_backfill_audit", metadata, autoload_with=bind)

    control_ids = _legacy_control_task_ids(bind, metadata)
    resolved_task_work: dict[object, object] = {}
    for task_id, project_id in bind.execute(sa.select(tasks.c.id, tasks.c.project_id)):
        candidates = [
            row[0]
            for row in bind.execute(
                sa.select(work.c.id).where(
                    work.c.project_id == project_id,
                    work.c.linked_task_id == task_id,
                )
            )
        ]
        if task_id in control_ids:
            status = "ignored_control"
            note = "Legacy Epic control Task links are not promoted to outcome ownership."
        elif len(candidates) == 1:
            status = "resolved"
            note = "Exactly one legacy linked_task_id candidate became canonical."
            resolved_task_work[task_id] = candidates[0]
            bind.execute(
                task_rel.insert().values(task_id=task_id, work_id=candidates[0], role="outcome")
            )
        elif candidates:
            status = "ambiguous"
            note = "Multiple legacy Work rows reference this Task; no winner was selected."
        else:
            status = "missing"
            note = "No legacy Work row references this Task."
        bind.execute(
            audit.insert().values(
                project_id=project_id,
                owner_type="task",
                owner_id=task_id,
                status=status,
                candidate_count=len(candidates),
                note=note,
            )
        )

    for epic_id, project_id in bind.execute(sa.select(epics.c.id, epics.c.project_id)):
        candidate_count = int(
            bind.scalar(
                sa.select(sa.func.count())
                .select_from(work)
                .where(
                    work.c.project_id == project_id,
                    work.c.linked_epic_id == epic_id,
                )
            )
            or 0
        )
        bind.execute(
            audit.insert().values(
                project_id=project_id,
                owner_type="epic_root",
                owner_id=epic_id,
                status="unresolved" if candidate_count else "missing",
                candidate_count=candidate_count,
                note=(
                    "linked_epic_id is a legacy association, not proof that a Work is the Epic root; "
                    "Phase 2 deliberately leaves root ownership unset."
                ),
            )
        )

    for item_id, task_id, kind in bind.execute(
        sa.select(plan_items.c.id, plan_items.c.task_id, plan_items.c.kind)
    ):
        if kind != "work" or task_id is None:
            continue
        work_id = resolved_task_work.get(task_id)
        if work_id is None:
            continue
        bind.execute(plan_rel.insert().values(plan_item_id=item_id, work_id=work_id))


def upgrade() -> None:
    _create_relation_tables()
    _backfill_relations()


def downgrade() -> None:
    op.drop_index("ix_work_relation_backfill_owner", table_name="work_relation_backfill_audit")
    op.drop_table("work_relation_backfill_audit")
    op.drop_index("ix_epic_plan_work_relations_work", table_name="epic_plan_work_relations")
    op.drop_table("epic_plan_work_relations")
    op.drop_index("ix_work_hierarchy_root", table_name="work_hierarchy")
    op.drop_index("ix_work_hierarchy_parent", table_name="work_hierarchy")
    op.drop_table("work_hierarchy")
    op.drop_index("ix_epic_work_relations_root", table_name="epic_work_relations")
    op.drop_table("epic_work_relations")
    op.drop_index("ix_task_work_relations_work", table_name="task_work_relations")
    op.drop_table("task_work_relations")
