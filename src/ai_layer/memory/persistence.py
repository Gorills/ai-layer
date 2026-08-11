from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ai_layer.db.models import ProjectFile, utcnow
from ai_layer.memory.identity import SourceSnapshot
from ai_layer.memory.versioning import SCANNER_SCHEMA_VERSION


def upsert_project_file(db: Session, payload: dict) -> None:
    """Idempotent source/file-row write; PostgreSQL/SQLite use native ON CONFLICT."""
    payload = dict(payload)
    payload.setdefault("content_sha256", payload.get("sha256", ""))
    payload.setdefault("mtime_ns", 0)
    payload.setdefault("ctime_ns", 0)
    payload.setdefault("indexed", True)
    payload.setdefault("scanner_schema", SCANNER_SCHEMA_VERSION)
    update_keys = (
        "language",
        "purpose",
        "imports",
        "risk_flags",
        "sha256",
        "content_sha256",
        "size_bytes",
        "mtime_ns",
        "ctime_ns",
        "indexed",
        "scanner_schema",
    )
    update_values = {key: payload[key] for key in update_keys}
    update_values["updated_at"] = utcnow()
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        stmt = pg_insert(ProjectFile).values(**payload).on_conflict_do_update(
            index_elements=[ProjectFile.project_id, ProjectFile.path],
            set_=update_values,
        )
        db.execute(stmt)
        return
    if dialect == "sqlite":
        stmt = sqlite_insert(ProjectFile).values(**payload).on_conflict_do_update(
            index_elements=["project_id", "path"],
            set_=update_values,
        )
        db.execute(stmt)
        return

    existing = db.scalar(
        select(ProjectFile).where(
            ProjectFile.project_id == payload["project_id"],
            ProjectFile.path == payload["path"],
        )
    )
    if existing is None:
        db.add(ProjectFile(**payload))
        return
    for key, value in update_values.items():
        setattr(existing, key, value)


def update_source_identity(row: ProjectFile, snapshot: SourceSnapshot) -> None:
    row.content_sha256 = snapshot.content_sha256
    row.size_bytes = snapshot.size
    row.mtime_ns = snapshot.mtime_ns
    row.ctime_ns = snapshot.ctime_ns


def file_state(rows: list[ProjectFile]) -> dict[str, dict[str, int | str | bool]]:
    return {
        row.path: {
            "size": int(row.size_bytes),
            "mtime_ns": int(row.mtime_ns),
            "ctime_ns": int(row.ctime_ns),
            "content_sha256": row.content_sha256,
            "indexed": bool(row.indexed),
            "scanner_schema": int(getattr(row, "scanner_schema", 0) or 0),
        }
        for row in rows
    }
