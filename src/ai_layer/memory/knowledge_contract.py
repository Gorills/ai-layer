from __future__ import annotations

import re
from datetime import datetime, timezone

from ai_layer.core.redaction import redact_secrets

KNOWLEDGE_KIND = "project-knowledge"
KNOWLEDGE_STATUSES = {"DRAFT", "VERIFIED", "STALE", "SUPERSEDED"}
KNOWLEDGE_CATEGORIES = {
    "overview",
    "subsystem",
    "runtime",
    "data",
    "integration",
    "deployment",
    "testing",
    "invariant",
    "fragile-area",
    "other",
}
MAX_TITLE_CHARS = 180
MAX_SUMMARY_CHARS = 2200
MAX_CLAIMS = 16
MAX_CLAIM_CHARS = 700
MAX_CONSTRAINTS = 12
MAX_UNKNOWNS = 8
MAX_EVIDENCE_PATHS = 24
_KEY_RE = re.compile(r"[^a-z0-9._/-]+")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_key(value: str) -> str:
    text = str(value or "").strip().casefold().replace(" ", "-")
    text = _KEY_RE.sub("-", text).strip("-./")
    if not text or len(text) > 160:
        raise ValueError("knowledge key must be a stable 1-160 character slug")
    return text


def _bounded_text(value: object, *, field: str, max_chars: int, required: bool = False) -> str:
    text = redact_secrets(str(value or "").strip())
    if required and not text:
        raise ValueError(f"knowledge: `{field}` is required")
    if len(text) > max_chars:
        raise ValueError(f"knowledge: `{field}` exceeds {max_chars} characters")
    return text


def _bounded_list(values: list[str] | None, *, field: str, max_items: int, max_chars: int) -> list[str]:
    result: list[str] = []
    for raw in list(values or []):
        text = _bounded_text(raw, field=field, max_chars=max_chars)
        if text and text not in result:
            result.append(text)
        if len(result) > max_items:
            raise ValueError(f"knowledge: `{field}` exceeds {max_items} items")
    return result


def normalize_card_input(
    *,
    key: str,
    category: str,
    title: str,
    summary: str,
    claims: list[str] | None,
    constraints: list[str] | None,
    unknowns: list[str] | None = None,
    evidence_paths: list[str] | None = None,
) -> dict:
    normalized_category = str(category or "").strip().casefold()
    if normalized_category not in KNOWLEDGE_CATEGORIES:
        raise ValueError(
            "knowledge: `category` must be one of: " + ", ".join(sorted(KNOWLEDGE_CATEGORIES))
        )
    paths = []
    for raw in list(evidence_paths or []):
        path = str(raw or "").strip().replace("\\", "/")
        if path.startswith("./"):
            path = path[2:]
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"knowledge: unsafe evidence path `{raw}`")
        if path not in paths:
            paths.append(path)
        if len(paths) > MAX_EVIDENCE_PATHS:
            raise ValueError(f"knowledge: `evidence_paths` exceeds {MAX_EVIDENCE_PATHS} items")
    if not paths:
        raise ValueError("knowledge: at least one repository evidence path is required")
    return {
        "key": normalize_key(key),
        "category": normalized_category,
        "title": _bounded_text(title, field="title", max_chars=MAX_TITLE_CHARS, required=True),
        "summary": _bounded_text(summary, field="summary", max_chars=MAX_SUMMARY_CHARS, required=True),
        "claims": _bounded_list(claims, field="claims", max_items=MAX_CLAIMS, max_chars=MAX_CLAIM_CHARS),
        "constraints": _bounded_list(
            constraints, field="constraints", max_items=MAX_CONSTRAINTS, max_chars=MAX_CLAIM_CHARS
        ),
        "unknowns": _bounded_list(unknowns, field="unknowns", max_items=MAX_UNKNOWNS, max_chars=MAX_CLAIM_CHARS),
        "evidence_paths": paths,
    }


def build_card_text(card: dict) -> str:
    lines = [
        f"Project knowledge card: {card['title']}",
        f"Category: {card['category']}",
        f"Summary: {card['summary']}",
    ]
    if card.get("claims"):
        lines.append("Verified claims:\n- " + "\n- ".join(card["claims"]))
    if card.get("constraints"):
        lines.append("Constraints/invariants:\n- " + "\n- ".join(card["constraints"]))
    if card.get("unknowns"):
        lines.append("Explicit unknowns:\n- " + "\n- ".join(card["unknowns"]))
    lines.append("Source pointers:\n- " + "\n- ".join(card["evidence_paths"]))
    return "\n".join(lines)


def public_card(item, *, include_content: bool = False) -> dict:
    meta = dict(getattr(item, "meta", None) or {})
    payload = {
        "id": str(item.id),
        "key": meta.get("knowledge_key"),
        "category": meta.get("category"),
        "title": item.title,
        "summary": meta.get("summary") or "",
        "claims": list(meta.get("claims") or []),
        "constraints": list(meta.get("constraints") or []),
        "unknowns": list(meta.get("unknowns") or []),
        "source_pointers": [e.get("path") for e in (meta.get("evidence") or []) if e.get("path")],
        "evidence": list(meta.get("evidence") or []),
        "status": meta.get("status") or "DRAFT",
        "confidence": meta.get("confidence") or "reviewed",
        "source_task_id": meta.get("source_task_id"),
        "validated_at": meta.get("validated_at"),
        "stale_reason": meta.get("stale_reason"),
        "provenance": "curated_project_knowledge",
    }
    if include_content:
        payload["content"] = item.content
    return payload
