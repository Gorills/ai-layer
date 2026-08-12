from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ai_layer.skills.service import skill_sections

NATIVE_DESCRIPTOR_VERSION = 2
NATIVE_MARKER = "<!-- AI-LAYER NATIVE SKILL v2"
GENERIC_DESCRIPTION_RE = re.compile(
    r"^(useful|helpful|general|generic|software development|coding|development)(\b|[ .:-])",
    re.IGNORECASE,
)


def _yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def native_descriptor_name(
    slug: str, *, project_root: str | Path | None = None, external_scope: bool = False
) -> str:
    if project_root is None or not external_scope:
        return slug
    root = str(Path(project_root).expanduser().resolve())
    key = hashlib.sha256(root.encode("utf-8")).hexdigest()[:10]
    base = f"ai-layer-{key}-{slug}"
    return base[:64].rstrip("-")


def validate_routing_description(slug: str, description: str) -> list[str]:
    text = " ".join(str(description or "").split())
    issues: list[str] = []
    if not text:
        issues.append("description is missing")
        return issues
    if len(text) < 28:
        issues.append("description is too short for reliable native routing")
    if len(text) > 180:
        issues.append("description is too long for metadata-first context economy")
    if GENERIC_DESCRIPTION_RE.search(text):
        issues.append("description starts with generic routing language")
    if len(set(re.findall(r"[a-zA-Z][a-zA-Z0-9+.#_-]{2,}", text.casefold()))) < 4:
        issues.append("description lacks concrete routing terms")
    if slug.replace("-", " ") == text.casefold().strip(" ."):
        issues.append("description merely repeats the skill name")
    return issues


def routing_overlap_warnings(skills: list[dict], *, threshold: float = 0.72) -> list[dict]:
    """Cheap lexical warning only; never used to route runtime work."""
    tokens: dict[str, set[str]] = {}
    stop = {"use", "for", "and", "the", "with", "that", "from", "across", "specific", "discipline"}
    for skill in skills:
        slug = str(skill.get("slug") or "")
        description = str((skill.get("meta") or {}).get("description") or "")
        tokens[slug] = {
            word
            for word in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#_-]{2,}", description.casefold())
            if word not in stop
        }
    warnings: list[dict] = []
    slugs = sorted(tokens)
    for index, left in enumerate(slugs):
        for right in slugs[index + 1 :]:
            union = tokens[left] | tokens[right]
            if not union:
                continue
            score = len(tokens[left] & tokens[right]) / len(union)
            if score >= threshold:
                warnings.append({"left": left, "right": right, "jaccard": round(score, 3)})
    return warnings


def validate_native_catalog(skills: list[dict]) -> dict:
    names: set[str] = set()
    issues: list[dict] = []
    for skill in skills:
        slug = str(skill.get("slug") or "")
        if not slug or slug in names:
            issues.append({"slug": slug, "problem": "duplicate or empty canonical slug"})
            continue
        names.add(slug)
        description = str((skill.get("meta") or {}).get("description") or "")
        for problem in validate_routing_description(slug, description):
            issues.append({"slug": slug, "problem": problem})
        sections = skill_sections(skill)
        if not sections:
            issues.append({"slug": slug, "problem": "canonical skill has no retrievable content"})
    return {
        "ok": not issues,
        "skills": len(skills),
        "issues": issues,
        "overlap_warnings": routing_overlap_warnings(skills),
    }


def render_native_skill(
    skill: dict,
    *,
    project_root: str | Path | None = None,
    external_scope: bool = False,
) -> str:
    """Render one host-native activation document with the complete authoritative skill body.

    The host still owns relevance selection from name/description metadata. Once selected,
    however, the model receives the actual professional guidance instead of a pointer that
    requires a second routing decision through ``skill_get``.
    """
    slug = str(skill["slug"])
    meta = skill.get("meta") or {}
    description = " ".join(str(meta.get("description") or "").split())
    problems = validate_routing_description(slug, description)
    if problems:
        raise ValueError(f"Skill `{slug}` is not safe to publish to native hosts: {problems}")

    content = str(skill.get("content") or "").strip()
    if not content:
        raise ValueError(f"Skill `{slug}` has no authoritative content to publish")

    name = native_descriptor_name(slug, project_root=project_root, external_scope=external_scope)
    root_key = (
        hashlib.sha256(str(Path(project_root).expanduser().resolve()).encode("utf-8")).hexdigest()[
            :10
        ]
        if project_root is not None
        else "-"
    )
    scope = "project" if project_root is not None else "global"
    marker = f"{NATIVE_MARKER} scope={scope} project={root_key} canonical={slug} -->"

    host_description = description
    if project_root is not None and external_scope:
        canonical_root = str(Path(project_root).expanduser().resolve())
        host_description = (
            f"{description} Activate only for the registered project at {canonical_root}."
        )

    return f"""---
name: {name}
description: {_yaml_scalar(host_description)}
---

{marker}
{content}
"""


def render_native_descriptor(
    skill: dict,
    *,
    project_root: str | Path | None = None,
    external_scope: bool = False,
) -> str:
    """Backward-compatible alias for callers using the pre-v2 renderer name."""
    return render_native_skill(
        skill,
        project_root=project_root,
        external_scope=external_scope,
    )
