from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Knowledge, Project, ProjectFile
from ai_layer.memory.embeddings import get_embedder
from ai_layer.memory.knowledge_contract import (
    KNOWLEDGE_KIND,
    build_card_text,
    normalize_card_input,
    public_card,
    utc_iso,
)

MIN_KNOWLEDGE_SCORE = 0.18


def _project_knowledge_rows(db: Session, project: Project) -> list[Knowledge]:
    return list(
        db.scalars(
            select(Knowledge)
            .where(Knowledge.project_id == project.id, Knowledge.kind == KNOWLEDGE_KIND)
            .order_by(Knowledge.updated_at.desc(), Knowledge.id)
        ).all()
    )


def knowledge_status(db: Session, project: Project) -> dict:
    rows = _project_knowledge_rows(db, project)
    counts = Counter(str((row.meta or {}).get("status") or "DRAFT") for row in rows)
    verified = [row for row in rows if str((row.meta or {}).get("status") or "DRAFT") == "VERIFIED"]
    category_counts = Counter(str((row.meta or {}).get("category") or "other") for row in verified)
    verified_categories = sorted(category_counts)
    overview_verified = any(str((row.meta or {}).get("category") or "") == "overview" for row in verified)
    subsystem_count = int(category_counts.get("subsystem", 0))
    return {
        "verified": counts.get("VERIFIED", 0),
        "stale": counts.get("STALE", 0),
        "draft": counts.get("DRAFT", 0),
        "superseded": counts.get("SUPERSEDED", 0),
        "verified_categories": verified_categories,
        "verified_category_counts": dict(sorted(category_counts.items())),
        "verified_subsystems": subsystem_count,
        "overview_verified": overview_verified,
        "baseline_ready": overview_verified,
        "onboarding_recommended": not overview_verified,
        "contract": (
            "Project knowledge is model-authored and review-gated. Scanner evidence is not semantic truth; "
            "current repository source remains authoritative."
        ),
    }


def list_knowledge(
    db: Session,
    project: Project,
    *,
    status: str | None = "VERIFIED",
    source_task_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    wanted_status = str(status or "").strip().upper()
    result = []
    for row in _project_knowledge_rows(db, project):
        meta = row.meta or {}
        if wanted_status and str(meta.get("status") or "DRAFT").upper() != wanted_status:
            continue
        if source_task_id and str(meta.get("source_task_id") or "") != str(source_task_id):
            continue
        result.append(public_card(row))
        if len(result) >= max(1, min(int(limit), 200)):
            break
    return result


def _evidence_for_paths(db: Session, project: Project, paths: list[str]) -> list[dict]:
    rows = db.scalars(
        select(ProjectFile).where(ProjectFile.project_id == project.id, ProjectFile.path.in_(paths))
    ).all()
    by_path = {row.path: row for row in rows}
    missing = [path for path in paths if path not in by_path]
    if missing:
        raise ValueError(
            "knowledge: evidence path(s) are not present in the latest deterministic scan: "
            + ", ".join(missing[:12])
        )
    return [
        {
            "path": path,
            "sha256": str(by_path[path].content_sha256 or by_path[path].sha256),
            "scanner_schema": int(by_path[path].scanner_schema or 0),
        }
        for path in paths
    ]


def upsert_draft(
    db: Session,
    project: Project,
    *,
    source_task_id: str,
    key: str,
    category: str,
    title: str,
    summary: str,
    claims: list[str] | None,
    constraints: list[str] | None,
    unknowns: list[str] | None = None,
    evidence_paths: list[str] | None = None,
) -> dict:
    card = normalize_card_input(
        key=key,
        category=category,
        title=title,
        summary=summary,
        claims=claims,
        constraints=constraints,
        unknowns=unknowns,
        evidence_paths=evidence_paths,
    )
    evidence = _evidence_for_paths(db, project, card["evidence_paths"])
    text = build_card_text(card)
    vectors = get_embedder().embed([text])
    if len(vectors) != 1:
        raise RuntimeError("Embedding provider returned an incomplete Project Knowledge vector batch.")
    vector = vectors[0]
    rows = _project_knowledge_rows(db, project)
    existing = next(
        (
            row for row in rows
            if (row.meta or {}).get("status") == "DRAFT"
            and (row.meta or {}).get("knowledge_key") == card["key"]
            and str((row.meta or {}).get("source_task_id") or "") == str(source_task_id)
        ),
        None,
    )
    meta = {
        "knowledge_key": card["key"],
        "category": card["category"],
        "summary": card["summary"],
        "claims": card["claims"],
        "constraints": card["constraints"],
        "unknowns": card["unknowns"],
        "evidence": evidence,
        "status": "DRAFT",
        "confidence": "pending_independent_review",
        "source_task_id": str(source_task_id),
        "validated_at": None,
        "stale_reason": None,
        "schema": 1,
    }
    if existing is None:
        existing = Knowledge(
            project_id=project.id,
            kind=KNOWLEDGE_KIND,
            title=card["title"],
            content=text,
            source_path=None,
            meta=meta,
            embedding=vector,
        )
        db.add(existing)
    else:
        existing.title = card["title"]
        existing.content = text
        existing.meta = meta
        existing.embedding = vector
    db.flush()
    return public_card(existing)


def has_task_drafts(db: Session, project: Project, task_id: str) -> bool:
    return any(
        (row.meta or {}).get("status") == "DRAFT"
        and str((row.meta or {}).get("source_task_id") or "") == str(task_id)
        for row in _project_knowledge_rows(db, project)
    )


def publish_task_drafts(db: Session, project: Project, task_id: str) -> dict:
    rows = _project_knowledge_rows(db, project)
    drafts = [
        row for row in rows
        if (row.meta or {}).get("status") == "DRAFT"
        and str((row.meta or {}).get("source_task_id") or "") == str(task_id)
    ]
    if not drafts:
        return {"published": 0, "superseded": 0}
    published = 0
    superseded = 0
    for draft in drafts:
        key = (draft.meta or {}).get("knowledge_key")
        for row in rows:
            if row.id == draft.id:
                continue
            meta = dict(row.meta or {})
            if meta.get("status") == "VERIFIED" and meta.get("knowledge_key") == key:
                meta["status"] = "SUPERSEDED"
                meta["superseded_at"] = utc_iso()
                meta["superseded_by"] = str(draft.id)
                row.meta = meta
                superseded += 1
        meta = dict(draft.meta or {})
        meta.update({
            "status": "VERIFIED",
            "confidence": "independent_review_passed",
            "validated_at": utc_iso(),
            "stale_reason": None,
        })
        draft.meta = meta
        published += 1
    db.flush()
    return {"published": published, "superseded": superseded}


def abandon_task_drafts(db: Session, project: Project, task_id: str) -> int:
    changed = 0
    for row in _project_knowledge_rows(db, project):
        meta = dict(row.meta or {})
        if meta.get("status") != "DRAFT" or str(meta.get("source_task_id") or "") != str(task_id):
            continue
        meta["status"] = "SUPERSEDED"
        meta["superseded_at"] = utc_iso()
        meta["stale_reason"] = "source task was cancelled before independent review"
        row.meta = meta
        changed += 1
    if changed:
        db.flush()
    return changed


def invalidate_stale_knowledge(db: Session, project: Project) -> int:
    rows = _project_knowledge_rows(db, project)
    files = db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id)).all()
    current = {row.path: str(row.content_sha256 or row.sha256) for row in files}
    changed = 0
    for row in rows:
        meta = dict(row.meta or {})
        if meta.get("status") != "VERIFIED":
            continue
        invalid = []
        for evidence in list(meta.get("evidence") or []):
            path = str(evidence.get("path") or "")
            if not path or current.get(path) != str(evidence.get("sha256") or ""):
                invalid.append(path or "<missing evidence path>")
        if not invalid:
            continue
        meta["status"] = "STALE"
        meta["stale_reason"] = "supporting repository evidence changed: " + ", ".join(invalid[:8])
        meta["stale_at"] = utc_iso()
        row.meta = meta
        changed += 1
    if changed:
        db.flush()
    return changed


def search_knowledge(db: Session, project: Project, query: str, *, status: str = "VERIFIED", limit: int = 6) -> list[dict]:
    vectors = get_embedder().embed([query])
    if len(vectors) != 1:
        raise RuntimeError("Embedding provider returned an incomplete Project Knowledge query vector batch.")
    vector = vectors[0]
    candidate_limit = max(40, int(limit) * 8)
    rows = db.execute(
        select(Knowledge, Knowledge.embedding.cosine_distance(vector).label("distance"))
        .where(Knowledge.project_id == project.id, Knowledge.kind == KNOWLEDGE_KIND)
        .order_by("distance")
        .limit(candidate_limit)
    ).all()
    wanted = str(status or "VERIFIED").upper()
    result = []
    for row, distance in rows:
        meta = row.meta or {}
        if str(meta.get("status") or "DRAFT").upper() != wanted:
            continue
        score = max(0.0, 1.0 - float(distance if distance is not None else 1.0))
        if score < MIN_KNOWLEDGE_SCORE:
            continue
        payload = public_card(row)
        payload["score"] = round(score, 4)
        result.append(payload)
        if len(result) >= max(1, min(int(limit), 20)):
            break
    return result


def relevant_source_pointers(cards: list[dict], *, limit: int = 20) -> list[str]:
    result: list[str] = []
    for card in cards:
        for path in list(card.get("source_pointers") or []):
            normalized = str(path or "").strip().replace("\\", "/")
            if normalized and normalized not in result:
                result.append(normalized)
            if len(result) >= limit:
                return result
    return result
