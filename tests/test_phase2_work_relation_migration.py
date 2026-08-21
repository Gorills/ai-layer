from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0019_canonical_work_relations.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("phase2_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_schema(metadata: sa.MetaData) -> dict[str, sa.Table]:
    return {
        "projects": sa.Table(
            "projects",
            metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
        ),
        "tasks": sa.Table(
            "tasks",
            metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("project_id", sa.Uuid(), nullable=False),
        ),
        "epics": sa.Table(
            "epics",
            metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("phase0_task_id", sa.Uuid(), nullable=True),
            sa.Column("drift_task_id", sa.Uuid(), nullable=True),
        ),
        "epic_plan_items": sa.Table(
            "epic_plan_items",
            metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("epic_id", sa.Uuid(), nullable=False),
            sa.Column("task_id", sa.Uuid(), nullable=True),
            sa.Column("kind", sa.String(16), nullable=False),
        ),
        "work_items": sa.Table(
            "work_items",
            metadata,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("linked_task_id", sa.Uuid(), nullable=True),
            sa.Column("linked_epic_id", sa.Uuid(), nullable=True),
        ),
    }


def test_phase2_migration_resolves_only_unambiguous_task_links() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    tables = _legacy_schema(metadata)
    metadata.create_all(engine)

    project_id = uuid4()
    resolved_task = uuid4()
    ambiguous_task = uuid4()
    missing_task = uuid4()
    control_task = uuid4()
    epic_id = uuid4()
    resolved_work = uuid4()
    ambiguous_work_a = uuid4()
    ambiguous_work_b = uuid4()
    weak_epic_work = uuid4()
    plan_item_id = uuid4()

    with engine.begin() as connection:
        connection.execute(tables["projects"].insert().values(id=project_id))
        connection.execute(
            tables["tasks"].insert(),
            [
                {"id": resolved_task, "project_id": project_id},
                {"id": ambiguous_task, "project_id": project_id},
                {"id": missing_task, "project_id": project_id},
                {"id": control_task, "project_id": project_id},
            ],
        )
        connection.execute(
            tables["epics"]
            .insert()
            .values(
                id=epic_id,
                project_id=project_id,
                phase0_task_id=control_task,
                drift_task_id=None,
            )
        )
        connection.execute(
            tables["epic_plan_items"]
            .insert()
            .values(
                id=plan_item_id,
                epic_id=epic_id,
                task_id=resolved_task,
                kind="work",
            )
        )
        connection.execute(
            tables["work_items"].insert(),
            [
                {
                    "id": resolved_work,
                    "project_id": project_id,
                    "linked_task_id": resolved_task,
                    "linked_epic_id": None,
                },
                {
                    "id": ambiguous_work_a,
                    "project_id": project_id,
                    "linked_task_id": ambiguous_task,
                    "linked_epic_id": None,
                },
                {
                    "id": ambiguous_work_b,
                    "project_id": project_id,
                    "linked_task_id": ambiguous_task,
                    "linked_epic_id": None,
                },
                {
                    "id": weak_epic_work,
                    "project_id": project_id,
                    "linked_task_id": None,
                    "linked_epic_id": epic_id,
                },
            ],
        )

        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        reflected = sa.MetaData()
        task_rel = sa.Table("task_work_relations", reflected, autoload_with=connection)
        epic_rel = sa.Table("epic_work_relations", reflected, autoload_with=connection)
        plan_rel = sa.Table("epic_plan_work_relations", reflected, autoload_with=connection)
        audit = sa.Table("work_relation_backfill_audit", reflected, autoload_with=connection)

        task_rows = connection.execute(
            sa.select(task_rel.c.task_id, task_rel.c.work_id, task_rel.c.role)
        ).all()
        assert task_rows == [(resolved_task, resolved_work, "outcome")]
        assert connection.execute(sa.select(epic_rel.c.epic_id)).all() == []
        assert connection.execute(sa.select(plan_rel.c.plan_item_id, plan_rel.c.work_id)).all() == [
            (plan_item_id, resolved_work)
        ]

        statuses = {
            (owner_type, owner_id): (status, candidate_count)
            for owner_type, owner_id, status, candidate_count in connection.execute(
                sa.select(
                    audit.c.owner_type,
                    audit.c.owner_id,
                    audit.c.status,
                    audit.c.candidate_count,
                )
            )
        }
        assert statuses[("task", resolved_task)] == ("resolved", 1)
        assert statuses[("task", ambiguous_task)] == ("ambiguous", 2)
        assert statuses[("task", missing_task)] == ("missing", 0)
        assert statuses[("task", control_task)] == ("ignored_control", 0)
        assert statuses[("epic_root", epic_id)] == ("unresolved", 1)
