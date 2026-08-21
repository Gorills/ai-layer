from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0020_server_owned_actions.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("phase3_action_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _phase2_schema(metadata: sa.MetaData) -> None:
    projects = sa.Table("projects", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    tasks = sa.Table(
        "tasks",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey(projects.c.id)),
    )
    sa.Table(
        "task_stages",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey(tasks.c.id)),
    )
    sa.Table(
        "work_items",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey(projects.c.id)),
    )


def test_phase3_action_migration_is_additive_and_does_not_invent_runtime_state() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    _phase2_schema(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert {"work_action_states", "work_action_submissions"} <= set(inspector.get_table_names())
        action_state = sa.Table("work_action_states", sa.MetaData(), autoload_with=connection)
        submissions = sa.Table("work_action_submissions", sa.MetaData(), autoload_with=connection)
        assert connection.scalar(sa.select(sa.func.count()).select_from(action_state)) == 0
        assert connection.scalar(sa.select(sa.func.count()).select_from(submissions)) == 0
        assert {column.name for column in action_state.columns} >= {
            "work_id",
            "project_id",
            "task_id",
            "stage_id",
            "state_version",
            "action_kind",
            "worker_kind",
            "worker_id",
            "action_token",
            "payload",
        }
        assert {column.name for column in submissions.columns} >= {
            "work_id",
            "action_token",
            "state_version",
            "report_fingerprint",
            "status",
            "response",
        }
