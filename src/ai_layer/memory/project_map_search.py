from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project
from ai_layer.db.navigation_models import ProjectNavigationSemantic
from ai_layer.memory.embeddings import get_embedder
from ai_layer.memory.project_map_semantics import (
    MIN_SEMANTIC_SEARCH_SCORE,
    _navigation_rows,
    _semantic_score_from_distance,
    _tokens,
)


def _lexical_score(
    row: ProjectNavigationSemantic, query_tokens: set[str]
) -> tuple[float, list[str]]:
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
    result["search_mode"] = (
        "hybrid_structural_semantic"
        if semantic_hits
        else structural_result.get("search_mode", "hybrid_metadata")
    )
    return result
