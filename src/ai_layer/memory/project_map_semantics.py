from __future__ import annotations

import re
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, RuntimeEvent, Task
from ai_layer.db.navigation_models import ProjectNavigation, ProjectNavigationSemantic
from ai_layer.memory.embeddings import get_embedder

MAX_ENTRIES = 40
MAX_SCOPE_PATHS = 120
MAX_LIST_ITEMS = 16
MAX_SEMANTIC_TEXT_CHARS = 5000
MIN_SEMANTIC_SEARCH_SCORE = 0.10
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TASK_KEY_RE = re.compile(r"^T-(\d{1,9})$", re.IGNORECASE)
_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "where",
    "what",
    "when",
    "this",
    "that",
    "code",
    "file",
    "find",
    "project",
    "как",
    "где",
    "что",
    "это",
    "для",
    "при",
    "или",
    "код",
    "файл",
    "найти",
    "проект",
}


def _tokens(value: object) -> set[str]:
    text = _CAMEL_RE.sub(" ", str(value or ""))
    text = text.replace("_", " ").replace("-", " ").casefold()
    return {
        token
        for token in _TOKEN_RE.findall(text)
        if len(token) >= 2 and token not in _STOP_WORDS
    }


def _semantic_score_from_distance(distance: float | None) -> float:
    value = 1.0 if distance is None else float(distance)
    return max(0.0, min(1.0, 1.0 - value))


def _normalize_path(value: object, *, field: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or raw.startswith("./"):
        raise ValueError(f"project_map_reconcile: `{field}` must be a canonical project-relative path")
    return path.as_posix()


def _text(value: object, *, field: str, max_chars: int, canonical_english: bool = False) -> str:
    result = " ".join(str(value or "").strip().split())
    if len(result) > max_chars:
        raise ValueError(
            f"project_map_reconcile: `{field}` exceeds the {max_chars}-character navigation limit"
        )
    if canonical_english and result and _CYRILLIC_RE.search(result):
        raise ValueError(
            f"project_map_reconcile: `{field}` is canonical semantic text and must be concise English; "
            "put Russian/domain wording in `domain_terms` instead"
        )
    return result


def _text_list(
    value: object,
    *,
    field: str,
    max_items: int = MAX_LIST_ITEMS,
    max_chars: int = 240,
    canonical_english: bool = False,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"project_map_reconcile: `{field}` must be a list")
    if len(value) > max_items:
        raise ValueError(
            f"project_map_reconcile: `{field}` has {len(value)} items; maximum is {max_items}"
        )
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _text(
            item,
            field=field,
            max_chars=max_chars,
            canonical_english=canonical_english,
        )
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        result.append(normalized)
    return result


def _path_list(value: object, *, field: str, max_items: int = MAX_LIST_ITEMS) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"project_map_reconcile: `{field}` must be a list")
    if len(value) > max_items:
        raise ValueError(
            f"project_map_reconcile: `{field}` has {len(value)} items; maximum is {max_items}"
        )
    return list(dict.fromkeys(_normalize_path(item, field=field) for item in value))


def _is_test_path(path: str) -> bool:
    name = PurePosixPath(path).name.casefold()
    parts = {part.casefold() for part in PurePosixPath(path).parts}
    return (
        "test" in parts
        or "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    )


def _task_for_key(db: Session, project: Project, task_key: str | None) -> tuple[Task | None, str]:
    rendered = str(task_key or "").strip().upper()
    if not rendered:
        return None, "agent"
    match = _TASK_KEY_RE.fullmatch(rendered)
    if not match:
        raise ValueError("project_map_reconcile: `source_task_key` must look like T-0001")
    task = db.scalar(
        select(Task).where(
            Task.project_id == project.id,
            Task.sequence == int(match.group(1)),
        )
    )
    if task is None:
        raise ValueError(f"project_map_reconcile: task `{rendered}` does not exist in this project")
    return task, f"T-{int(task.sequence):04d}"


def _navigation_rows(db: Session, project: Project) -> dict[str, ProjectNavigation]:
    rows = db.scalars(
        select(ProjectNavigation).where(ProjectNavigation.project_id == project.id)
    ).all()
    return {row.path: row for row in rows}


def _validate_symbols(entry: dict, navigation: ProjectNavigation) -> list[str]:
    requested = _text_list(
        entry.get("important_symbols"), field="important_symbols", max_items=16, max_chars=240
    )
    known: set[str] = set()
    for symbol in list(navigation.symbols or []):
        if not isinstance(symbol, dict):
            continue
        for key in ("name", "qualified_name"):
            value = str(symbol.get(key) or "").strip()
            if value:
                known.add(value)
    unknown = [item for item in requested if item not in known]
    if unknown:
        raise ValueError(
            "project_map_reconcile: important_symbols must exist in the current scanner map for "
            f"`{navigation.path}`; unknown: {unknown[:5]}"
        )
    return requested


def _validate_related_paths(
    entry: dict,
    *,
    navigation_paths: set[str],
) -> tuple[list[str], list[str]]:
    related_files = _path_list(entry.get("related_files"), field="related_files", max_items=16)
    related_tests = _path_list(entry.get("related_tests"), field="related_tests", max_items=16)
    unknown = [path for path in [*related_files, *related_tests] if path not in navigation_paths]
    if unknown:
        raise ValueError(
            "project_map_reconcile: related paths must exist in the current Project Map; "
            f"unknown: {unknown[:5]}"
        )
    invalid_tests = [path for path in related_tests if not _is_test_path(path)]
    if invalid_tests:
        raise ValueError(
            "project_map_reconcile: related_tests must look like test paths; "
            f"invalid: {invalid_tests[:5]}"
        )
    return related_files, related_tests


def _normalize_entry(
    raw: object,
    *,
    navigation_rows: dict[str, ProjectNavigation],
) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("project_map_reconcile: every `entries` item must be an object")
    path = _normalize_path(raw.get("path"), field="entries.path")
    navigation = navigation_rows.get(path)
    if navigation is None:
        raise ValueError(
            f"project_map_reconcile: `{path}` is not in the current scanner-owned Project Map"
        )
    purpose = _text(
        raw.get("purpose"), field="purpose", max_chars=320, canonical_english=True
    )
    responsibilities = _text_list(
        raw.get("responsibilities"),
        field="responsibilities",
        max_items=12,
        max_chars=280,
        canonical_english=True,
    )
    domain_terms = _text_list(
        raw.get("domain_terms"), field="domain_terms", max_items=20, max_chars=120
    )
    important_symbols = _validate_symbols(raw, navigation)
    related_files, related_tests = _validate_related_paths(
        raw, navigation_paths=set(navigation_rows)
    )
    navigation_hints = _text_list(
        raw.get("navigation_hints"),
        field="navigation_hints",
        max_items=8,
        max_chars=280,
        canonical_english=True,
    )
    if not any((purpose, responsibilities, domain_terms, important_symbols, navigation_hints)):
        raise ValueError(
            f"project_map_reconcile: semantic entry for `{path}` has no useful navigation content"
        )
    return {
        "path": path,
        "purpose": purpose,
        "responsibilities": responsibilities,
        "domain_terms": domain_terms,
        "important_symbols": important_symbols,
        "related_files": related_files,
        "related_tests": related_tests,
        "navigation_hints": navigation_hints,
        "content_sha256": navigation.content_sha256,
    }


def _semantic_text(item: dict) -> str:
    lines = [f"Path: {item['path']}"]
    if item["purpose"]:
        lines.append("Purpose: " + item["purpose"])
    for field, label in (
        ("responsibilities", "Responsibilities"),
        ("domain_terms", "Domain terms"),
        ("important_symbols", "Important symbols"),
        ("related_files", "Related files"),
        ("related_tests", "Related tests"),
        ("navigation_hints", "Navigation hints"),
    ):
        values = item[field]
        if values:
            lines.append(f"{label}: " + "; ".join(values))
    return "\n".join(lines)[:MAX_SEMANTIC_TEXT_CHARS]


def _embed(text: str) -> list[float] | None:
    try:
        vectors = get_embedder().embed([text])
    except Exception:
        return None
    return vectors[0] if len(vectors) == 1 else None


def _upsert_semantic_row(
    db: Session,
    project: Project,
    item: dict,
    *,
    task: Task | None,
    source_ref: str,
) -> None:
    row = db.scalar(
        select(ProjectNavigationSemantic).where(
            ProjectNavigationSemantic.project_id == project.id,
            ProjectNavigationSemantic.path == item["path"],
        )
    )
    if row is None:
        row = ProjectNavigationSemantic(project_id=project.id, path=item["path"])
        db.add(row)
    row.purpose = item["purpose"]
    row.responsibilities = item["responsibilities"]
    row.domain_terms = item["domain_terms"]
    row.important_symbols = item["important_symbols"]
    row.related_files = item["related_files"]
    row.related_tests = item["related_tests"]
    row.navigation_hints = item["navigation_hints"]
    row.semantic_text = _semantic_text(item)
    row.content_sha256 = item["content_sha256"]
    row.source_kind = "task" if task is not None else "agent"
    row.source_ref = source_ref
    row.source_task_id = task.id if task is not None else None
    row.embedding = _embed(row.semantic_text)


def _remove_semantic_rows(
    db: Session,
    project: Project,
    paths: list[str],
) -> list[str]:
    removed: list[str] = []
    for path in paths:
        row = db.scalar(
            select(ProjectNavigationSemantic).where(
                ProjectNavigationSemantic.project_id == project.id,
                ProjectNavigationSemantic.path == path,
            )
        )
        if row is None:
            continue
        db.delete(row)
        removed.append(path)
    return removed


def _record_reconciliation_event(
    db: Session,
    project: Project,
    *,
    task: Task | None,
    source_ref: str,
    updated: list[str],
    removed: list[str],
    scope_paths: list[str],
    no_changes_reason: str,
) -> None:
    aggregate_type = "task" if task is not None else "project"
    aggregate_id = str(task.id if task is not None else project.id)
    db.add(
        RuntimeEvent(
            project_id=project.id,
            event_type="ProjectMapReconciled",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor_id="agent:project-map",
            actor_kind="agent",
            interface="mcp",
            payload={
                "source_ref": source_ref,
                "updated": len(updated),
                "removed": len(removed),
                "updated_paths": updated,
                "removed_paths": removed,
                "scope_paths": scope_paths,
                "no_changes_reason": no_changes_reason,
                "language_policy": "canonical English semantics; exact source identifiers; multilingual domain terms",
            },
        )
    )


def reconcile_project_map(
    db: Session,
    project: Project,
    *,
    entries: list[dict] | None,
    remove_paths: list[str] | None,
    scope_paths: list[str] | None,
    source_task_key: str | None,
    no_changes_reason: str | None,
) -> dict:
    """Replace semantic breadcrumbs for explicitly reconciled paths without touching scanner data."""
    raw_entries = list(entries or [])
    if len(raw_entries) > MAX_ENTRIES:
        raise ValueError(f"project_map_reconcile: maximum {MAX_ENTRIES} entries per call")
    raw_scope = list(scope_paths or [])
    if len(raw_scope) > MAX_SCOPE_PATHS:
        raise ValueError(f"project_map_reconcile: maximum {MAX_SCOPE_PATHS} scope paths per call")
    navigation_rows = _navigation_rows(db, project)
    normalized = [
        _normalize_entry(item, navigation_rows=navigation_rows) for item in raw_entries
    ]
    removals = _path_list(remove_paths or [], field="remove_paths", max_items=MAX_ENTRIES)
    scope = _path_list(raw_scope, field="scope_paths", max_items=MAX_SCOPE_PATHS)
    if not scope:
        scope = list(dict.fromkeys([item["path"] for item in normalized] + removals))
    reason = _text(no_changes_reason, field="no_changes_reason", max_chars=500)
    if not normalized and not removals and not reason:
        raise ValueError(
            "project_map_reconcile: provide semantic entries/removals or a factual `no_changes_reason`"
        )
    task, source_ref = _task_for_key(db, project, source_task_key)
    for item in normalized:
        _upsert_semantic_row(db, project, item, task=task, source_ref=source_ref)
    removed = _remove_semantic_rows(db, project, removals)
    updated = [item["path"] for item in normalized]
    _record_reconciliation_event(
        db,
        project,
        task=task,
        source_ref=source_ref,
        updated=updated,
        removed=removed,
        scope_paths=scope,
        no_changes_reason=reason,
    )
    db.flush()
    return {
        "ok": True,
        "source_ref": source_ref,
        "updated": updated,
        "removed": removed,
        "scope_paths": scope,
        "no_changes_reason": reason,
        "contract": (
            "Scanner-owned structure was not modified. Canonical semantic descriptions are English; "
            "source identifiers stay exact; multilingual user/domain aliases belong in domain_terms."
        ),
    }


def semantic_map_status(db: Session, project: Project) -> dict:
    navigation = _navigation_rows(db, project)
    rows = list(
        db.scalars(
            select(ProjectNavigationSemantic).where(
                ProjectNavigationSemantic.project_id == project.id
            )
        ).all()
    )
    current = 0
    stale = 0
    orphaned = 0
    for row in rows:
        structural = navigation.get(row.path)
        if structural is None:
            orphaned += 1
        elif structural.content_sha256 == row.content_sha256:
            current += 1
        else:
            stale += 1
    total_navigation = len(navigation)
    return {
        "semantic_entries": len(rows),
        "semantic_current": current,
        "semantic_stale": stale,
        "semantic_orphaned": orphaned,
        "semantic_missing": max(0, total_navigation - current - stale),
        "semantic_current_coverage": (
            round(current / total_navigation, 4) if total_navigation else 0.0
        ),
        "language_policy": {
            "canonical_semantics": "English",
            "source_identifiers": "exact repository spelling",
            "domain_terms": "multilingual when materially useful",
        },
    }


def _lexical_score(row: ProjectNavigationSemantic, query_tokens: set[str]) -> tuple[float, list[str]]:
    if not query_tokens:
        return 0.0, []
    fields = {
        "domain terms": _tokens(" ".join(row.domain_terms or [])),
        "important symbols": _tokens(" ".join(row.important_symbols or [])),
        "responsibility/purpose": _tokens(
            " ".join([row.purpose, *(row.responsibilities or []), *(row.navigation_hints or [])])
        ),
    }
    size = len(query_tokens)
    weighted = (
        len(query_tokens & fields["domain terms"]) / size * 0.50
        + len(query_tokens & fields["important symbols"]) / size * 0.28
        + len(query_tokens & fields["responsibility/purpose"]) / size * 0.22
    )
    matched = [label for label, tokens in fields.items() if query_tokens & tokens]
    if len(query_tokens & fields["domain terms"]) >= 2:
        weighted += 0.12
    return min(1.0, weighted), matched


def search_semantic_map(
    db: Session,
    project: Project,
    query: str,
    *,
    limit: int = 20,
) -> list[dict]:
    query = str(query or "").strip()
    if not query:
        return []
    limit = max(1, min(int(limit), 40))
    navigation = _navigation_rows(db, project)
    rows = list(
        db.scalars(
            select(ProjectNavigationSemantic).where(
                ProjectNavigationSemantic.project_id == project.id
            )
        ).all()
    )
    vector_scores: dict[str, float] = {}
    try:
        vectors = get_embedder().embed([query])
    except Exception:
        vectors = []
    if len(vectors) == 1:
        candidates = db.execute(
            select(
                ProjectNavigationSemantic,
                ProjectNavigationSemantic.embedding.cosine_distance(vectors[0]).label("distance"),
            )
            .where(
                ProjectNavigationSemantic.project_id == project.id,
                ProjectNavigationSemantic.embedding.is_not(None),
            )
            .order_by("distance")
            .limit(max(40, limit * 4))
        ).all()
        for row, distance in candidates:
            vector_scores[row.path] = _semantic_score_from_distance(distance)
    query_tokens = _tokens(query)
    ranked: list[dict] = []
    for row in rows:
        structural = navigation.get(row.path)
        if structural is None:
            continue
        lexical, matched_fields = _lexical_score(row, query_tokens)
        semantic = vector_scores.get(row.path, 0.0)
        freshness = "current" if structural.content_sha256 == row.content_sha256 else "stale"
        score = min(1.0, semantic * 0.62 + lexical * 0.38 + (0.08 if lexical >= 0.45 else 0.0))
        if freshness == "stale":
            score *= 0.72
        if score < MIN_SEMANTIC_SEARCH_SCORE:
            continue
        reasons = [f"semantic {label} match" for label in matched_fields]
        if semantic > 0:
            reasons.append("multilingual semantic enrichment match")
        if freshness == "stale":
            reasons.append("semantic enrichment is stale; verify current source")
        ranked.append(
            {
                "path": row.path,
                "language": structural.language,
                "score": round(score, 4),
                "why": reasons,
                "semantic": {
                    "purpose": row.purpose,
                    "responsibilities": list(row.responsibilities or []),
                    "domain_terms": list(row.domain_terms or []),
                    "important_symbols": list(row.important_symbols or []),
                    "related_files": list(row.related_files or []),
                    "related_tests": list(row.related_tests or []),
                    "navigation_hints": list(row.navigation_hints or []),
                    "freshness": freshness,
                    "source": row.source_ref or row.source_kind,
                },
            }
        )
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
    return ranked[:limit]


def merge_project_search(
    structural_result: dict,
    semantic_hits: list[dict],
    *,
    limit: int,
) -> dict:
    by_path: dict[str, dict] = {
        str(item["path"]): dict(item) for item in structural_result.get("matches") or []
    }
    for semantic in semantic_hits:
        path = str(semantic["path"])
        current = by_path.get(path)
        if current is None:
            current = {
                "path": path,
                "language": semantic.get("language"),
                "purpose": "",
                "symbols": [],
                "imports": [],
                "risk_flags": [],
                "score": 0.0,
                "why": [],
            }
            by_path[path] = current
        structural_score = float(current.get("score") or 0.0)
        semantic_score = float(semantic.get("score") or 0.0)
        combined = max(
            structural_score,
            semantic_score,
            min(1.0, structural_score * 0.55 + semantic_score * 0.65),
        )
        current["score"] = round(combined, 4)
        current["semantic"] = semantic.get("semantic")
        current["why"] = list(
            dict.fromkeys([*(current.get("why") or []), *(semantic.get("why") or [])])
        )
    ranked = sorted(
        by_path.values(), key=lambda item: (-float(item.get("score") or 0.0), str(item["path"]))
    )[: max(1, min(int(limit), 20))]
    related_tests = list(structural_result.get("related_tests") or [])
    for item in ranked:
        semantic = item.get("semantic") or {}
        related_tests.extend(semantic.get("related_tests") or [])
    result = dict(structural_result)
    result["matches"] = ranked
    result["related_tests"] = list(dict.fromkeys(related_tests))[:12]
    result["search_mode"] = "hybrid_structural_semantic" if semantic_hits else structural_result.get(
        "search_mode", "hybrid_metadata"
    )
    result["language_contract"] = (
        "Queries may be Russian, English or mixed. Canonical semantic descriptions are English; "
        "exact code identifiers are preserved; domain_terms may contain useful multilingual aliases."
    )
    return result
