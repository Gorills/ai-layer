from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ai_layer.db.models import Decision, Knowledge, Project, ProjectFile
from ai_layer.db.navigation_models import ProjectNavigation
from ai_layer.memory.embeddings import get_embedder
from ai_layer.memory.identity import ChangeSet, SourceSnapshot, classify_changes
from ai_layer.memory.knowledge_contract import KNOWLEDGE_KIND
from ai_layer.memory.knowledge_store import invalidate_stale_knowledge
from ai_layer.memory.navigation import build_navigation_document
from ai_layer.memory.persistence import file_state, update_source_identity, upsert_project_file
from ai_layer.memory.project_state import refresh_project_snapshot, sync_project_metadata
from ai_layer.memory.source import (
    extract_imports,
    infer_purpose,
    language_for,
    prepare_index_text,
    redact_secrets,
    risk_flags,
)
from ai_layer.memory.versioning import SCANNER_SCHEMA_VERSION

METADATA_ONLY_PURPOSE = "Metadata-tracked source excluded from deterministic parsing."
LEGACY_SCANNER_KINDS = {"file", "architecture", "project-intelligence"}
SEMANTIC_REEMBED_BATCH_SIZE = 64


@dataclass
class ScanStats:
    files: int
    source_files: int
    knowledge_items: int
    languages: dict[str, int]
    dependencies: dict[str, list[str]]
    selected_skills: list[str]
    file_state: dict[str, dict[str, int | str | bool]]
    changes: dict = field(default_factory=dict)
    hashes_calculated: int = 0
    embeddings_reused: int = 0
    embeddings_regenerated: int = 0
    decisions_reembedded: int = 0
    knowledge_reembedded: int = 0
    legacy_source_knowledge_removed: int = 0
    knowledge_cards_staled: int = 0


def _identity_payload(
    project: Project, snapshot: SourceSnapshot, *, indexed: bool, **semantic
) -> dict:
    return {
        "project_id": project.id,
        "path": snapshot.path,
        "language": semantic.get("language"),
        "purpose": semantic.get("purpose", METADATA_ONLY_PURPOSE),
        "imports": semantic.get("imports", []),
        "risk_flags": semantic.get("risk_flags", []),
        "sha256": semantic.get("sha256", snapshot.content_sha256),
        "content_sha256": snapshot.content_sha256,
        "size_bytes": snapshot.size,
        "mtime_ns": snapshot.mtime_ns,
        "ctime_ns": snapshot.ctime_ns,
        "indexed": indexed,
        "scanner_schema": SCANNER_SCHEMA_VERSION,
    }


def _delete_source_rows(db: Session, project: Project, paths: list[str]) -> None:
    if not paths:
        return
    # Compatibility cleanup for pre-v0.11 raw-source semantic rows.
    db.execute(
        delete(Knowledge).where(
            Knowledge.project_id == project.id,
            Knowledge.source_path.in_(paths),
        )
    )
    db.execute(
        delete(ProjectNavigation).where(
            ProjectNavigation.project_id == project.id,
            ProjectNavigation.path.in_(paths),
        )
    )
    db.execute(
        delete(ProjectFile).where(
            ProjectFile.project_id == project.id,
            ProjectFile.path.in_(paths),
        )
    )


def _replace_changed_source(
    db: Session,
    project: Project,
    snapshot: SourceSnapshot,
    existing: ProjectFile | None,
    *,
    force_reparse: bool = False,
) -> dict | None:
    """Refresh deterministic evidence and return metadata-only Project Map input when needed."""
    rel = snapshot.path
    prepared = prepare_index_text(rel, snapshot.text) if snapshot.text is not None else None
    if prepared is None:
        upsert_project_file(
            db,
            _identity_payload(
                project,
                snapshot,
                indexed=False,
                language=language_for(Path(rel)),
            ),
        )
        db.execute(
            delete(Knowledge).where(
                Knowledge.project_id == project.id,
                Knowledge.source_path == rel,
            )
        )
        db.execute(
            delete(ProjectNavigation).where(
                ProjectNavigation.project_id == project.id,
                ProjectNavigation.path == rel,
            )
        )
        return None

    semantic_sha256 = hashlib.sha256(prepared.encode("utf-8", errors="replace")).hexdigest()
    if (
        existing is not None
        and bool(getattr(existing, "indexed", True))
        and existing.sha256 == semantic_sha256
        and int(getattr(existing, "scanner_schema", 0) or 0) == SCANNER_SCHEMA_VERSION
        and not force_reparse
    ):
        update_source_identity(existing, snapshot)
        return None

    language = language_for(Path(rel))
    imports = [redact_secrets(str(value)) for value in extract_imports(prepared)]
    purpose = infer_purpose(rel, prepared, language)
    risks = risk_flags(rel, prepared)
    upsert_project_file(
        db,
        _identity_payload(
            project,
            snapshot,
            indexed=True,
            language=language,
            purpose=purpose,
            imports=imports,
            risk_flags=risks,
            sha256=semantic_sha256,
        ),
    )
    # A changed source version invalidates legacy source chunks and its old navigation row.
    db.execute(
        delete(Knowledge).where(
            Knowledge.project_id == project.id,
            Knowledge.source_path == rel,
        )
    )
    db.execute(
        delete(ProjectNavigation).where(
            ProjectNavigation.project_id == project.id,
            ProjectNavigation.path == rel,
        )
    )
    return build_navigation_document(
        path=rel,
        text=prepared,
        language=language,
        purpose=purpose,
        imports=imports,
        risk_flags=risks,
        content_sha256=snapshot.content_sha256,
        scanner_schema=SCANNER_SCHEMA_VERSION,
    )


def _apply_source_changes(
    db: Session,
    project: Project,
    previous: dict[str, ProjectFile],
    changes: ChangeSet,
    *,
    force_reparse: bool = False,
) -> list[dict]:
    _delete_source_rows(db, project, changes.deleted)
    documents: list[dict] = []
    if force_reparse:
        for rel in changes.metadata_only:
            document = _replace_changed_source(
                db,
                project,
                changes.snapshots[rel],
                previous.get(rel),
                force_reparse=True,
            )
            if document is not None:
                documents.append(document)
    else:
        for rel in changes.metadata_only:
            row = previous.get(rel)
            if row is not None:
                update_source_identity(row, changes.snapshots[rel])
    for rel in changes.content_changed:
        document = _replace_changed_source(
            db,
            project,
            changes.snapshots[rel],
            previous.get(rel),
            force_reparse=force_reparse,
        )
        if document is not None:
            documents.append(document)
    return documents


def _store_navigation_documents(db: Session, project: Project, documents: list[dict]) -> int:
    if not documents:
        return 0
    embedder = get_embedder()
    count = 0
    for offset in range(0, len(documents), SEMANTIC_REEMBED_BATCH_SIZE):
        batch = documents[offset : offset + SEMANTIC_REEMBED_BATCH_SIZE]
        vectors = embedder.embed([str(item["navigation_text"]) for item in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding provider returned an incomplete Project Map batch.")
        for item, vector in zip(batch, vectors, strict=True):
            db.add(
                ProjectNavigation(
                    project_id=project.id,
                    path=item["path"],
                    language=item["language"],
                    purpose=item["purpose"],
                    imports=item["imports"],
                    risk_flags=item["risk_flags"],
                    symbols=item["symbols"],
                    navigation_text=item["navigation_text"],
                    content_sha256=item["content_sha256"],
                    scanner_schema=item["scanner_schema"],
                    embedding=vector,
                )
            )
        count += len(batch)
        db.flush()
    return count


def _purge_legacy_scanner_knowledge(db: Session, project: Project) -> int:
    ids = list(
        db.scalars(
            select(Knowledge.id).where(
                Knowledge.project_id == project.id,
                Knowledge.kind.in_(sorted(LEGACY_SCANNER_KINDS)),
            )
        ).all()
    )
    if ids:
        db.execute(delete(Knowledge).where(Knowledge.id.in_(ids)))
    return len(ids)


def _embed_rows_in_batches(db: Session, rows, *, text_attr: str) -> int:
    embedder = get_embedder()
    count = 0
    for offset in range(0, len(rows), SEMANTIC_REEMBED_BATCH_SIZE):
        batch = rows[offset : offset + SEMANTIC_REEMBED_BATCH_SIZE]
        vectors = embedder.embed([str(getattr(row, text_attr)) for row in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding provider returned an incomplete semantic-memory batch.")
        for row, vector in zip(batch, vectors, strict=True):
            row.embedding = vector
        count += len(batch)
        db.flush()
    return count


def _reembed_semantic_memory(db: Session, project: Project) -> tuple[int, int]:
    decisions = list(
        db.scalars(
            select(Decision).where(Decision.project_id == project.id).order_by(Decision.id)
        ).all()
    )
    knowledge = list(
        db.scalars(
            select(Knowledge)
            .where(Knowledge.project_id == project.id, Knowledge.kind == KNOWLEDGE_KIND)
            .order_by(Knowledge.id)
        ).all()
    )
    return (
        _embed_rows_in_batches(db, decisions, text_attr="decision"),
        _embed_rows_in_batches(db, knowledge, text_attr="content"),
    )


def scan_project(
    db: Session,
    project: Project,
    root: Path,
    *,
    reembed_decisions: bool = False,
    force_reparse: bool = False,
) -> ScanStats:
    """Refresh repository evidence plus a metadata-only Project Map; never persist source bodies."""
    legacy_before = int(
        db.scalar(
            select(func.count(Knowledge.id)).where(
                Knowledge.project_id == project.id,
                Knowledge.kind.in_(sorted(LEGACY_SCANNER_KINDS)),
            )
        )
        or 0
    )
    previous_rows = db.scalars(
        select(ProjectFile).where(ProjectFile.project_id == project.id)
    ).all()
    previous = {row.path: row for row in previous_rows}
    changes = classify_changes(root, previous_rows, force_verify_all=force_reparse)
    navigation_documents = _apply_source_changes(
        db, project, previous, changes, force_reparse=force_reparse
    )
    navigation_regenerated = _store_navigation_documents(db, project, navigation_documents)
    db.flush()

    rows, languages, dependencies, summary, intelligence, selected = refresh_project_snapshot(
        db, project, root
    )
    sync_project_metadata(
        db,
        project,
        languages=languages,
        dependencies=dependencies,
        summary=summary,
        intelligence=intelligence,
        selected=selected,
    )
    _purge_legacy_scanner_knowledge(db, project)
    staled = invalidate_stale_knowledge(db, project)
    decisions_reembedded, knowledge_reembedded = (
        _reembed_semantic_memory(db, project) if reembed_decisions else (0, 0)
    )
    db.flush()

    rows = list(
        db.scalars(
            select(ProjectFile)
            .where(ProjectFile.project_id == project.id)
            .order_by(ProjectFile.path)
            .execution_options(populate_existing=True)
        ).all()
    )
    navigation_items = int(
        db.scalar(
            select(func.count(ProjectNavigation.id)).where(
                ProjectNavigation.project_id == project.id
            )
        )
        or 0
    )
    knowledge_items = int(
        db.scalar(select(func.count(Knowledge.id)).where(Knowledge.project_id == project.id)) or 0
    )
    return ScanStats(
        files=sum(1 for row in rows if row.indexed),
        source_files=len(rows),
        knowledge_items=knowledge_items,
        languages=languages,
        dependencies=dependencies,
        selected_skills=[slug for slug, _ in selected],
        file_state=file_state(rows),
        changes=changes.summary(),
        hashes_calculated=changes.hashes_calculated,
        embeddings_reused=max(0, navigation_items - navigation_regenerated),
        embeddings_regenerated=navigation_regenerated,
        decisions_reembedded=decisions_reembedded,
        knowledge_reembedded=knowledge_reembedded,
        legacy_source_knowledge_removed=legacy_before,
        knowledge_cards_staled=staled,
    )
