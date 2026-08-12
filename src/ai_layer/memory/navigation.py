from __future__ import annotations

import ast
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Knowledge, Project, ProjectFile
from ai_layer.memory.embeddings import get_embedder

NAVIGATION_KIND = "project-navigation"
MAX_SYMBOLS_PER_FILE = 80
MAX_NAVIGATION_TEXT_CHARS = 6000
MIN_PROJECT_SEARCH_SCORE = 0.10
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ROUTE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "api_route",
    "websocket",
}
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


def _symbol(
    name: str,
    kind: str,
    line: int,
    *,
    qualified_name: str | None = None,
    signature: str = "",
    detail: str = "",
) -> dict:
    return {
        "name": name,
        "qualified_name": qualified_name or name,
        "kind": kind,
        "line_start": max(1, int(line or 1)),
        "signature": signature[:320],
        "detail": detail[:320],
    }


def _python_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Keep parameter names only; never persist default expressions or annotations."""
    names = [item.arg for item in [*node.args.posonlyargs, *node.args.args]]
    positional_defaults = len(node.args.defaults)
    if positional_defaults:
        for index in range(len(names) - positional_defaults, len(names)):
            names[index] += "=..."
    if node.args.vararg:
        names.append("*" + node.args.vararg.arg)
    elif node.args.kwonlyargs:
        names.append("*")
    for item, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        names.append(item.arg + ("=..." if default is not None else ""))
    if node.args.kwarg:
        names.append("**" + node.args.kwarg.arg)
    return f"{node.name}({', '.join(names)})"[:320]


def _python_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        method = func.attr if isinstance(func, ast.Attribute) else ""
        if method not in _ROUTE_METHODS:
            continue
        route = ""
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            value = decorator.args[0].value
            if isinstance(value, str):
                route = value[:200]
        return f"{method.upper()} {route}".strip()
    return ""


def _python_symbols(text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    result: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            result.append(_symbol(node.name, "class", node.lineno, signature=f"class {node.name}"))
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                result.append(
                    _symbol(
                        child.name,
                        "method",
                        child.lineno,
                        qualified_name=f"{node.name}.{child.name}",
                        signature=_python_signature(child),
                    )
                )
                if len(result) >= MAX_SYMBOLS_PER_FILE:
                    return result
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            route = _python_route(node)
            result.append(
                _symbol(
                    node.name,
                    "route" if route else "function",
                    node.lineno,
                    signature=_python_signature(node),
                    detail=route,
                )
            )
        if len(result) >= MAX_SYMBOLS_PER_FILE:
            break
    return result[:MAX_SYMBOLS_PER_FILE]


def _regex_symbols(text: str, language: str | None) -> list[dict]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    if language in {"javascript", "typescript", "vue", "svelte"}:
        patterns = [
            ("class", re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")),
            ("function", re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")),
            ("function", re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")),
        ]
    elif language == "php":
        patterns = [
            ("class", re.compile(r"\bclass\s+([A-Za-z_][\w]*)")),
            ("function", re.compile(r"\bfunction\s+([A-Za-z_][\w]*)\s*\(")),
        ]
    elif language == "go":
        patterns = [
            ("function", re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)\s*\(")),
            ("type", re.compile(r"\btype\s+([A-Za-z_][\w]*)\s+(?:struct|interface)\b")),
        ]
    elif language == "rust":
        patterns = [
            ("function", re.compile(r"\b(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*\(")),
            ("type", re.compile(r"\b(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_][\w]*)")),
        ]
    elif language in {"java", "kotlin", "csharp", "cpp", "c"}:
        patterns = [("type", re.compile(r"\b(?:class|interface|struct|enum)\s+([A-Za-z_][\w]*)"))]

    result: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    sample = text[:200_000]
    for kind, pattern in patterns:
        for match in pattern.finditer(sample):
            line = sample.count("\n", 0, match.start()) + 1
            key = (kind, match.group(1), line)
            if key in seen:
                continue
            seen.add(key)
            result.append(_symbol(match.group(1), kind, line))
            if len(result) >= MAX_SYMBOLS_PER_FILE:
                return sorted(result, key=lambda item: (item["line_start"], item["name"]))
    return sorted(result, key=lambda item: (item["line_start"], item["name"]))


def extract_symbols(text: str, language: str | None) -> list[dict]:
    """Extract bounded navigation metadata only; source bodies are never persisted."""
    return _python_symbols(text) if language == "python" else _regex_symbols(text, language)


def build_navigation_document(
    *,
    path: str,
    text: str,
    language: str | None,
    purpose: str,
    imports: list[str],
    risk_flags: list[str],
) -> dict:
    symbols = extract_symbols(text, language)
    lines = [f"Path: {path}", f"Language: {language or 'text'}", f"Purpose: {purpose}"]
    if symbols:
        lines.append("Symbols:")
        for item in symbols:
            suffix = f" — {item['detail']}" if item.get("detail") else ""
            lines.append(
                f"- {item['kind']}: {item['qualified_name']} {item.get('signature') or ''}{suffix}".strip()
            )
    if imports:
        lines.append("Imports: " + ", ".join(imports[:40]))
    if risk_flags:
        lines.append("Risk flags: " + ", ".join(risk_flags[:20]))
    return {
        "path": path,
        "title": f"Project Map: {path}",
        "content": "\n".join(lines)[:MAX_NAVIGATION_TEXT_CHARS],
        "meta": {
            "schema": 1,
            "path": path,
            "language": language,
            "purpose": purpose,
            "imports": imports[:80],
            "risk_flags": risk_flags[:40],
            "symbols": symbols,
            "provenance": "deterministic_navigation_metadata",
        },
    }


def _navigation_rows(db: Session, project: Project) -> list[Knowledge]:
    return list(
        db.scalars(
            select(Knowledge)
            .where(Knowledge.project_id == project.id, Knowledge.kind == NAVIGATION_KIND)
            .order_by(Knowledge.source_path, Knowledge.id)
        ).all()
    )


def project_map_status(db: Session, project: Project) -> dict:
    files = list(db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id)).all())
    navigation = _navigation_rows(db, project)
    return {
        "files": len(files),
        "indexed_files": sum(1 for row in files if bool(row.indexed)),
        "navigation_files": len(navigation),
        "symbol_count": sum(len(list((row.meta or {}).get("symbols") or [])) for row in navigation),
        "scanner_schema": max((int(row.scanner_schema or 0) for row in files), default=0),
        "contract": (
            "Project Map stores paths, symbols, imports and compact purposes, never source bodies. "
            "Current repository source remains authoritative."
        ),
    }


def _lexical_score(row: ProjectFile, meta: dict, query_tokens: set[str]) -> tuple[float, list[dict]]:
    symbols = [dict(item) for item in list(meta.get("symbols") or []) if isinstance(item, dict)]
    path_tokens = _tokens(row.path)
    purpose_tokens = _tokens(meta.get("purpose") or row.purpose)
    import_tokens = _tokens(" ".join(str(item) for item in list(meta.get("imports") or row.imports or [])))
    symbol_tokens: set[str] = set()
    matched_symbols: list[dict] = []
    for item in symbols:
        tokens = _tokens(
            " ".join(
                str(item.get(key) or "")
                for key in ("name", "qualified_name", "signature", "detail")
            )
        )
        symbol_tokens |= tokens
        if query_tokens & tokens:
            matched_symbols.append(item)
    if not query_tokens:
        return 0.0, []
    size = len(query_tokens)
    score = min(
        1.0,
        len(query_tokens & path_tokens) / size * 0.42
        + len(query_tokens & symbol_tokens) / size * 0.42
        + len(query_tokens & purpose_tokens) / size * 0.12
        + len(query_tokens & import_tokens) / size * 0.04,
    )
    if matched_symbols:
        score = min(1.0, score + 0.18)
    return score, matched_symbols[:8]


def _related_tests(rows: list[ProjectFile], hits: list[dict], *, limit: int = 8) -> list[str]:
    interest: set[str] = set()
    for hit in hits[:4]:
        interest |= _tokens(hit.get("path"))
        for symbol in hit.get("symbols") or []:
            interest |= _tokens(symbol.get("name"))
    scored: list[tuple[int, str]] = []
    for row in rows:
        path = str(row.path or "")
        name = Path(path).name.casefold()
        is_test = (
            "test" in Path(path).parts
            or name.startswith("test_")
            or ".test." in name
            or ".spec." in name
        )
        overlap = len(interest & _tokens(path)) if is_test else 0
        if overlap:
            scored.append((overlap, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:limit]]


def search_project_map(db: Session, project: Project, query: str, *, limit: int = 8) -> dict:
    query = str(query or "").strip()
    if not query:
        raise ValueError("project_search: `query` is required")
    limit = max(1, min(int(limit), 20))
    query_tokens = _tokens(query)
    files = list(
        db.scalars(
            select(ProjectFile)
            .where(ProjectFile.project_id == project.id, ProjectFile.indexed.is_(True))
            .order_by(ProjectFile.path)
        ).all()
    )
    navigation = _navigation_rows(db, project)
    nav_by_path = {str(row.source_path or ""): row for row in navigation if row.source_path}
    semantic_scores: dict[str, float] = {}
    if navigation:
        vectors = get_embedder().embed([query])
        if len(vectors) != 1:
            raise RuntimeError("Embedding provider returned an incomplete Project Map query vector.")
        candidates = db.execute(
            select(Knowledge, Knowledge.embedding.cosine_distance(vectors[0]).label("distance"))
            .where(Knowledge.project_id == project.id, Knowledge.kind == NAVIGATION_KIND)
            .order_by("distance")
            .limit(max(40, limit * 8))
        ).all()
        for nav, distance in candidates:
            path = str(nav.source_path or "")
            if path:
                semantic_scores[path] = max(0.0, 1.0 - float(distance or 1.0))

    ranked: list[dict] = []
    for row in files:
        nav = nav_by_path.get(str(row.path))
        meta = dict(nav.meta or {}) if nav is not None else {}
        lexical, matched_symbols = _lexical_score(row, meta, query_tokens)
        semantic = semantic_scores.get(str(row.path), 0.0)
        score = min(1.0, semantic * 0.60 + lexical * 0.40 + (0.08 if lexical >= 0.45 else 0.0))
        if score < MIN_PROJECT_SEARCH_SCORE and not matched_symbols:
            continue
        symbols = matched_symbols or [
            dict(item)
            for item in list(meta.get("symbols") or [])[:6]
            if isinstance(item, dict)
        ]
        reasons = []
        if matched_symbols:
            reasons.append("matching symbol names")
        if lexical > 0:
            reasons.append("path/purpose/import match")
        if semantic > 0:
            reasons.append("semantic navigation metadata match")
        ranked.append(
            {
                "path": row.path,
                "language": meta.get("language") or row.language,
                "purpose": meta.get("purpose") or row.purpose,
                "symbols": symbols[:8],
                "imports": list(meta.get("imports") or row.imports or [])[:10],
                "risk_flags": list(meta.get("risk_flags") or row.risk_flags or [])[:8],
                "score": round(score, 4),
                "why": reasons or ["nearest Project Map match"],
            }
        )
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
    hits = ranked[:limit]
    return {
        "query": query,
        "matches": hits,
        "related_tests": _related_tests(files, hits),
        "map": project_map_status(db, project),
        "search_mode": "hybrid_metadata" if navigation else "lexical_metadata",
        "source_contract": (
            "Use these results as breadcrumbs. Open only relevant current source with host-native tools "
            "before making code-truth claims or edits."
        ),
    }
