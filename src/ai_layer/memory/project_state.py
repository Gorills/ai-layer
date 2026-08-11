from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, ProjectFile
from ai_layer.memory.intelligence import (
    build_project_intelligence,
    compact_architecture_summary,
)
from ai_layer.memory.source import parse_dependencies


def refresh_project_snapshot(
    db: Session,
    project: Project,
    root: Path,
) -> tuple[list[ProjectFile], dict, dict, str, dict, list[tuple[str, str]]]:
    rows = db.scalars(
        select(ProjectFile)
        .where(ProjectFile.project_id == project.id)
        .order_by(ProjectFile.path)
        .execution_options(populate_existing=True)
    ).all()
    languages = dict(
        Counter(row.language for row in rows if row.indexed and row.language).most_common()
    )
    dependencies = parse_dependencies(root)
    intelligence = build_project_intelligence(root, rows, languages, dependencies)
    summary = compact_architecture_summary(root, intelligence)
    selected: list[tuple[str, str]] = []  # Native hosts own skill relevance; keep scan shape compatible.
    return rows, languages, dependencies, summary, intelligence, selected


def sync_project_metadata(
    db: Session,
    project: Project,
    *,
    languages: dict,
    dependencies: dict,
    summary: str,
    intelligence: dict,
    selected: list[tuple[str, str]],
) -> None:
    project.languages = languages
    project.dependencies = dependencies
    project.architecture_summary = summary
    project.project_intelligence = intelligence
    # ``ProjectSkill`` rows from pre-native-routing releases are retained as historical data only.
    # New scans do not create, delete, or consult them for relevance decisions.
    del selected
