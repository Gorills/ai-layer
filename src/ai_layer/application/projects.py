from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from ai_layer.core.registry import is_project_forgotten, register_project
from ai_layer.core.service import (
    get_project,
    init_project,
    project_info,
    remove_project_registration,
    scan_registered_project,
)
from ai_layer.db.models import Project
from ai_layer.db.session import session_scope
from ai_layer.observability.domain_events import append_event


def hydrate_registry_from_database() -> dict:
    imported = 0
    skipped_missing = 0
    skipped_forgotten = 0
    with session_scope() as db:
        projects = db.scalars(select(Project)).all()
        for project in projects:
            if not Path(project.root_path).exists():
                skipped_missing += 1
                continue
            if is_project_forgotten(project.root_path):
                skipped_forgotten += 1
                continue
            register_project(project.root_path, str(project.id), project.name)
            imported += 1
    return {
        "ok": True,
        "imported": imported,
        "skipped_missing": skipped_missing,
        "skipped_forgotten": skipped_forgotten,
    }


def initialize_project(
    path: str | Path, name: str | None = None, *, private: bool = False, external: bool = False
) -> dict:
    with session_scope() as db:
        project = init_project(db, path, name, private=private, external=external)
        append_event(
            db,
            event_type="ProjectRegistered",
            project=project,
            aggregate_type="project",
            aggregate_id=str(project.id),
            payload={
                "root_path": project.root_path,
                "name": project.name,
                "private": private,
                "external": external,
            },
        )
        return {"id": str(project.id), "root_path": project.root_path, "name": project.name}


def scan_project(path: str | Path) -> dict:
    with session_scope() as db:
        return scan_registered_project(db, path)


def get_project_info(path: str | Path) -> dict:
    with session_scope() as db:
        return project_info(db, path)


def remove_project(path: str | Path) -> dict:
    with session_scope() as db:
        return remove_project_registration(db, path)


def project_identity(path: str | Path) -> dict:
    with session_scope() as db:
        project = get_project(db, path)
        return {"id": str(project.id), "root_path": project.root_path, "name": project.name}
