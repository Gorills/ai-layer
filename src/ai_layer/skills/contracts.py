from __future__ import annotations

import re
from typing import Iterable

import yaml

from ai_layer.skills.common import _sha_text
from ai_layer.skills.constants import (
    HIGH_RISK_PATTERNS, MAX_SKILL_BYTES, MEDIUM_RISK_PATTERNS, SLUG_RE,
)

def _frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        parts = text.split("---\n", 2)
        if len(parts) == 3:
            loaded = yaml.safe_load(parts[1]) or {}
            return (loaded if isinstance(loaded, dict) else {}), parts[2].strip()
    return {}, text.strip()


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value[:128].strip("-")


def _first_heading(body: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    return match.group(1).strip() if match else ""


def _infer_terms(*parts: str) -> list[str]:
    words: list[str] = []
    for part in parts:
        for word in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#_-]{2,}", part.casefold()):
            if word not in words:
                words.append(word)
    return words[:16]


def normalize_skill_text(
    text: str,
    *,
    slug: str | None = None,
    description: str | None = None,
    task_terms: Iterable[str] | None = None,
    always: bool = False,
) -> tuple[str, dict, str]:
    """Normalize canonical skill content without creating a runtime relevance policy.

    ``task_terms`` and ``always`` remain accepted for transport compatibility with older clients.
    Task terms are folded into diagnostic-search keywords; ``always`` has no routing effect because
    host-native Agent Skills own activation. Always-on policy belongs in Rules, not Skills.
    """
    data = text.encode("utf-8")
    if len(data) > MAX_SKILL_BYTES:
        raise ValueError(f"Skill is too large: {len(data)} bytes > {MAX_SKILL_BYTES}")
    meta, body = _frontmatter(text)
    heading = _first_heading(body)
    wanted_slug = (slug or str(meta.get("slug") or meta.get("name") or "") or _slugify(heading)).strip()
    wanted_slug = _slugify(wanted_slug)
    if not wanted_slug or not SLUG_RE.fullmatch(wanted_slug):
        raise ValueError("Skill slug could not be inferred safely; provide an explicit lowercase slug.")
    wanted_description = (description or str(meta.get("description") or "") or heading or f"Project expertise: {wanted_slug}").strip()
    if len(wanted_description) > 500:
        wanted_description = wanted_description[:500].rstrip()

    normalized_meta = dict(meta)
    normalized_meta["slug"] = wanted_slug
    normalized_meta["description"] = wanted_description
    if normalized_meta.get("kind") not in {"core", "domain", "capability", "stack"}:
        normalized_meta["kind"] = "capability"

    # Remove fields that belonged to the retired AI Layer relevance router.
    legacy_terms = list(normalized_meta.get("task_terms") or [])
    legacy_entry = list(normalized_meta.get("autoload_sections") or [])
    for key in ("activation", "task_terms", "autoload_sections", "routing", "priority", "requires", "evidence_languages", "intelligence_domains"):
        normalized_meta.pop(key, None)

    keywords = [str(item).strip().casefold() for item in (normalized_meta.get("keywords") or []) if str(item).strip()]
    keywords.extend(str(item).strip().casefold() for item in legacy_terms if str(item).strip())
    keywords.extend(str(item).strip().casefold() for item in (task_terms or []) if str(item).strip())
    if not keywords:
        keywords = _infer_terms(wanted_slug.replace("-", " "), wanted_description, heading)
    if keywords:
        normalized_meta["keywords"] = list(dict.fromkeys(keywords))[:32]

    if "entry_sections" not in normalized_meta:
        headings = re.findall(r"(?m)^##\s+(.+?)\s*$", body)
        preferred = [name for name in legacy_entry if name in headings]
        if not preferred:
            preferred = [name for name in ("Core contract", "Mandatory rules", "Apply when", "Decision rules") if name in headings]
        if not preferred and headings:
            preferred = headings[:1]
        if preferred:
            normalized_meta["entry_sections"] = preferred[:3]

    header = yaml.safe_dump(normalized_meta, allow_unicode=True, sort_keys=False).strip()
    normalized = f"---\n{header}\n---\n\n{body.strip()}\n"
    origin = "native" if bool(meta.get("slug") or meta.get("name")) else "inferred"
    return normalized, normalized_meta, origin


def validate_skill_text(text: str) -> dict:
    if "\x00" in text:
        raise ValueError("Skill contains NUL bytes")
    normalized, meta, metadata_origin = normalize_skill_text(text)
    body = _frontmatter(normalized)[1]
    issues: list[dict] = []
    for pattern, reason in HIGH_RISK_PATTERNS:
        if re.search(pattern, body):
            issues.append({"severity": "high", "reason": reason})
    for pattern, reason in MEDIUM_RISK_PATTERNS:
        if re.search(pattern, body):
            issues.append({"severity": "medium", "reason": reason})
    sections = re.findall(r"(?m)^##\s+(.+?)\s*$", body)
    if not body.strip():
        issues.append({"severity": "high", "reason": "skill body is empty"})
    risk = "high" if any(x["severity"] == "high" for x in issues) else "medium" if issues else "low"
    return {
        "slug": meta["slug"],
        "description": meta.get("description", ""),
        "kind": meta.get("kind"),
        "metadata_origin": metadata_origin,
        "risk": risk,
        "issues": issues,
        "sections": sections,
        "sha256": _sha_text(normalized),
        "bytes": len(normalized.encode("utf-8")),
        "normalized": normalized,
        "meta": meta,
    }
