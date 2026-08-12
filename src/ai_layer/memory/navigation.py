from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Project, ProjectFile
from ai_layer.memory.embeddings import get_embedder

MAX_SYMBOLS_PER_FILE = 80
MAX_NAVIGATION_TEXT_CHARS = 6000
MIN_PROJECT_SEARCH_SCORE = 0.10
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "api_route", "websocket"}
_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
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


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _symbol(
    *,
    name: str,
    kind: str,
    line_start: int,
    line_end: int | None = None,
    qualified_name: str | None = None,
    signature: str = "",
    detail: str = "",
) -> dict:
    return {
        "name": name,
        "qualified_name": qualified_name or name,
        "kind": kind,
        "line_start": max(1, int(line_start or 1)),
        "line_end": max(1, int(line_end or line_start or 1)),
        "signature": signature[:500],
        "detail": detail[:500],
    }


def _python_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args: list[str] = []
    positional = [*node.args.posonlyargs, *node.args.args]
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    for item, default in zip(positional, defaults, strict=True):
        value = item.arg
        if default is not None:
            try:
                value += "=" + ast.unparse(default)[:80]
            except Exception:
                value += "=..."
        args.append(value)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    elif node.args.kwonlyargs:
        args.append("*")
    for item, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        value = item.arg
        if default is not None:
            try:
                value += "=" + ast.unparse(default)[:80]
            except Exception:
                value += "=..."
        args.append(value)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return ", ".join(args)[:420]


def _python_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        method = func.attr if isinstance(func, ast.Attribute) else ""
        if method not in _ROUTE_METHODS:
            continue
        route = ""
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            route = str(decorator.args[0].value or "")
        return method.upper(), route
    return None


def _python_symbols(text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    result: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            result.append(
                _symbol(
                    name=node.name,
                    kind="class",
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    signature=f"class {node.name}",
                )
            )
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                result.append(
                    _symbol(
                        name=child.name,
                        qualified_name=f"{node.name}.{child.name}",
                        kind="method",
                        line_start=child.lineno,
                        line_end=getattr(child, "end_lineno", child.lineno),
                        signature=f"{child.name}({_python_args(child)})",
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            route = _python_route(node)
            result.append(
                _symbol(
                    name=node.name,
                    kind="route" if route else "function",
                    line_start=node.lineno,
                    line_end=getattr(node, "end_lineno", node.lineno),
                    signature=f"{node.name}({_python_args(node)})",
                    detail=(f"{route[0]} {route[1]}" if route else ""),
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
            ("function", re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)")),
            ("function", re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")),
        ]
    elif language == "php":
        patterns = [
            ("class", re.compile(r"\bclass\s+([A-Za-z_][\w]*)")),
            ("function", re.compile(r"\bfunction\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)")),
        ]
    elif language == "go":
        patterns = [
            ("function", re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)\s*\(([^)]*)\)")),
            ("type", re.compile(r"\btype\s+([A-Za-z_][\w]*)\s+(?:struct|interface)\b")),
        ]
    elif language == "rust":
        patterns = [
            ("function", re.compile(r"\b(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)")),
            ("type", re.compile(r"\b(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_][\w]*)")),
        ]
    elif language in {"java", "kotlin", "csharp", "cpp", "c"}:
        patterns = [
            ("type", re.compile(r"\b(?:class|interface|struct|enum)\s+([A-Za-z_][\w]*)")),
        ]
    result: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    for kind, pattern in patterns:
        for match in pattern.finditer(text[:200_000]):
            name = match.group(1)
            line = _line_for_offset(text, match.start())
            key = (kind, name, line)
            if key in seen:
                continue
            seen.add(key)
            args = match.group(2).strip() if (match.lastindex or 0) >= 2 else ""
            result.append(
                _symbol(
                    name=name,
                    kind=kind,
                    line_start=line,
                    signature=(f"{name}({args})" if args else name),
                )
            )
            if len(result) >= MAX_SYMBOLS_PER_FILE:
                return result
    return sorted(result, key=lambda item: (int(item["line_start"]), str(item["name"])))


def extract_symbols(text: str, language: str | None) -> list[dict]:
    """Extract bounded navigation metadata only; source bodies are never persisted."""
    if language == "python":
        return _python_symbols(text)
    return _regex_symbols(text, language)


def build_navigation_text(
    *,
    path: str,
    language: str | None,
    purpose: str,
    imports: list[str],
    risk_flags: list[str],
    symbols: list[dict],
) -> str:
    lines = [f"Path: {path}", f"Language: {language or 'text'}", f"Purpose: {purpose}"]
    if symbols:
        lines.append("Symbols:")
        for item in symbols[:MAX_SYMBOLS_PER_FILE]:
            detail = str(item.get("detail") or "")
            suffix = f" — {detail}" if detail else ""
            lines.append(
                f"- {item.get('kind')}: {item.get('qualified_name') or item.get('name')} "
                f"{item.get('signature') or ''}{suffix}".strip()
            )
    if imports:
        lines.append("Imports: " + ", ".join(imports[:40]))
    if risk_flags:
        lines.append("Risk flags: " + ", ".join(risk_flags[:20]))
    return "\n".join(lines)[:MAX_NAVIGATION_TEXT_CHARS]


def build_navigation_metadata(
    *, path: str, text: str, language: str | None, purpose: str, imports: list[str], risk_flags: list[str]
) -> dict:
    symbols = extract_symbols(text, language)
    return {
        "symbols": symbols,
        "navigation_text": build_navigation_text(
            path=path,
            language=language,
            purpose=purpose,
            imports=imports,
            risk_flags=risk_flags,
            symbols=symbols,
        ),
    }


def project_map_status(db: Session, project: Project) -> dict:
    rows = list(
        db.scalars(
            select(ProjectFile)
            .where(ProjectFile.project_id == project.id)
            .order_by(ProjectFile.path)
        ).all()
    )
    indexed = [row for row in rows if bool(row.indexed)]
    return {
        "files": len(rows),
        "indexed_files": len(indexed),
        "symbol_count": sum(len(list(row.symbols or [])) for row in indexed),
        "semantic_navigation_files": sum(
            1 for row in indexed if getattr(row, "navigation_embedding", None) is not None
        ),
        "scanner_schema": max((int(row.scanner_schema or 0) for row in rows), default=0),
        "contract": (
            "Project Map stores navigation metadata (paths, symbols, imports and compact purposes), not source bodies. "
            "Current repository source remains authoritative."
        ),
    }


def _lexical_score(row: ProjectFile, query: str, query_tokens: set[str]) -> tuple[float, list[str], list[dict]]:
    path = str(row.path or "")
    purpose = str(row.purpose or "")
    imports = [str(item) for item in list(row.imports or [])]
    symbols = [dict(item) for item in list(row.symbols or []) if isinstance(item, dict)]
    path_tokens = _tokens(path)
    purpose_tokens = _tokens(purpose)
    import_tokens = _tokens(" ".join(imports))
    matched_symbols: list[dict] = []
    symbol_tokens: set[str] = set()
    for item in symbols:
        item_tokens = _tokens(
            " ".join(
                [
                    str(item.get("name") or ""),
                    str(item.get("qualified_name") or ""),
                    str(item.get("signature") or ""),
                    str(item.get("detail") or ""),
                ]
            )
        )
        symbol_tokens |= item_tokens
        if query_tokens & item_tokens:
            matched_symbols.append(item)
    if not query_tokens:
        return 0.0, [], []
    overlap_path = len(query_tokens & path_tokens) / len(query_tokens)
    overlap_symbol = len(query_tokens & symbol_tokens) / len(query_tokens)
    overlap_purpose = len(query_tokens & purpose_tokens) / len(query_tokens)
    overlap_import = len(query_tokens & import_tokens) / len(query_tokens)
    score = min(
        1.0,
        overlap_path * 0.42
        + overlap_symbol * 0.42
        + overlap_purpose * 0.12
        + overlap_import * 0.04,
    )
    normalized_query = query.casefold().strip()
    reasons: list[str] = []
    if normalized_query and normalized_query in path.casefold():
        score = min(1.0, score + 0.28)
        reasons.append("query appears directly in path")
    if matched_symbols:
        score = min(1.0, score + 0.18)
        reasons.append("matching symbol names/signatures")
    if overlap_path:
        reasons.append("path token match")
    if overlap_purpose:
        reasons.append("file purpose match")
    if overlap_import:
        reasons.append("import/dependency match")
    return score, reasons[:4], matched_symbols[:10]


def _related_tests(rows: list[ProjectFile], top_hits: list[dict], *, limit: int = 8) -> list[str]:
    if not top_hits:
        return []
    interest: set[str] = set()
    for hit in top_hits[:4]:
        interest |= _tokens(hit.get("path"))
        for symbol in hit.get("symbols") or []:
            interest |= _tokens(symbol.get("name"))
    scored: list[tuple[int, str]] = []
    for row in rows:
        path = str(row.path or "")
        name = Path(path).name.casefold()
        is_test = "test" in Path(path).parts or name.startswith("test_") or ".test." in name or ".spec." in name
        if not is_test:
            continue
        overlap = len(interest & _tokens(path))
        if overlap:
            scored.append((overlap, path))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:limit]]


def search_project_map(
    db: Session, project: Project, query: str, *, limit: int = 8
) -> dict:
    query = str(query or "").strip()
    if not query:
        raise ValueError("project_search: `query` is required")
    limit = max(1, min(int(limit), 20))
    query_tokens = _tokens(query)
    rows = list(
        db.scalars(
            select(ProjectFile)
            .where(ProjectFile.project_id == project.id, ProjectFile.indexed.is_(True))
            .order_by(ProjectFile.path)
        ).all()
    )
    semantic_scores: dict[str, float] = {}
    semantic_available = any(
        getattr(row, "navigation_embedding", None) is not None for row in rows
    )
    if semantic_available:
        vector = get_embedder().embed([query])
        if len(vector) != 1:
            raise RuntimeError("Embedding provider returned an incomplete Project Map query vector.")
        candidates = db.execute(
            select(
                ProjectFile,
                ProjectFile.navigation_embedding.cosine_distance(vector[0]).label("distance"),
            )
            .where(
                ProjectFile.project_id == project.id,
                ProjectFile.indexed.is_(True),
                ProjectFile.navigation_embedding.is_not(None),
            )
            .order_by("distance")
            .limit(max(40, limit * 8))
        ).all()
        for row, distance in candidates:
            semantic_scores[str(row.path)] = max(
                0.0, 1.0 - float(distance if distance is not None else 1.0)
            )

    ranked: list[dict] = []
    for row in rows:
        lexical, reasons, matched_symbols = _lexical_score(row, query, query_tokens)
        semantic = semantic_scores.get(str(row.path), 0.0)
        score = min(1.0, semantic * 0.60 + lexical * 0.40)
        if lexical >= 0.45:
            score = min(1.0, score + 0.08)
        if score < MIN_PROJECT_SEARCH_SCORE and not matched_symbols:
            continue
        if semantic > 0:
            reasons.append("semantic navigation metadata match")
        symbols = matched_symbols or [
            dict(item) for item in list(row.symbols or [])[:6] if isinstance(item, dict)
        ]
        ranked.append(
            {
                "path": row.path,
                "language": row.language,
                "purpose": row.purpose,
                "symbols": symbols[:8],
                "imports": list(row.imports or [])[:10],
                "risk_flags": list(row.risk_flags or [])[:8],
                "score": round(score, 4),
                "semantic_score": round(semantic, 4) if semantic else None,
                "lexical_score": round(lexical, 4),
                "why": reasons[:4] or ["nearest Project Map match"],
            }
        )
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["path"])))
    hits = ranked[:limit]
    return {
        "query": query,
        "matches": hits,
        "related_tests": _related_tests(rows, hits),
        "map": project_map_status(db, project),
        "search_mode": "hybrid_metadata" if semantic_available else "lexical_metadata",
        "source_contract": (
            "Use these results as breadcrumbs. Open only the relevant current source with host-native tools before making code-truth claims or edits."
        ),
    }
