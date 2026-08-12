#!/usr/bin/env python3
"""Executable native-first activation and depth gate for every bundled production skill."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_layer.skills.native import render_native_skill, validate_native_catalog  # noqa: E402
from ai_layer.skills.service import (  # noqa: E402
    _parse_skill_text,
    skill_section_content,
    skill_sections,
)

SKILLS = ROOT / "src" / "ai_layer" / "builtin_skills"
VALID_KINDS = {"core", "domain", "capability", "stack"}
OBSOLETE_ROUTING_KEYS = {
    "activation",
    "task_terms",
    "autoload_sections",
    "routing",
    "priority",
    "requires",
    "evidence_languages",
    "intelligence_domains",
}

# Bundled skills are production instructions for coding agents, not routing stubs.
# The floor intentionally protects depth, semantic entry sections and native activation.
# Context economy comes from host relevance selection and exact-section rereads, not from
# replacing an already-selected professional skill with a pointer or clipped fragment.
MIN_CONTENT_CHARS = 7000
MIN_CONTENT_WORDS = 850
MIN_SECTIONS = 10
REQUIRED_SECTIONS = {
    "Apply when",
    "Core contract",
    "Evidence to inspect",
    "Decision rules",
    "Workflow",
    "Implementation patterns",
    "Failure modes",
    "Verification",
    "Completion criteria",
    "Related skills and escalation",
}
ENTRY_SECTIONS = ("Apply when", "Core contract", "Decision rules")
BODY_OVERLAP_ERROR = 0.75
BODY_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{3,}", re.IGNORECASE)
BODY_STOP_WORDS = {
    "about",
    "after",
    "also",
    "before",
    "between",
    "could",
    "does",
    "each",
    "every",
    "from",
    "have",
    "into",
    "must",
    "only",
    "other",
    "rather",
    "should",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "this",
    "through",
    "using",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "would",
}


def _body_tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in BODY_TOKEN_RE.findall(text)
        if token.casefold() not in BODY_STOP_WORDS
    }


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))


def _check_depth(skill: dict, errors: list[str]) -> None:
    slug = str(skill["slug"])
    content = str(skill.get("content") or "").strip()
    sections = skill_sections(skill)
    section_names = set(sections)

    if len(content) < MIN_CONTENT_CHARS:
        errors.append(
            f"{slug}: bundled skill is too shallow "
            f"({len(content)} chars; minimum {MIN_CONTENT_CHARS})"
        )
    words = _word_count(content)
    if words < MIN_CONTENT_WORDS:
        errors.append(
            f"{slug}: bundled skill is too terse ({words} words; minimum {MIN_CONTENT_WORDS})"
        )
    if len(sections) < MIN_SECTIONS:
        errors.append(
            f"{slug}: bundled skill has too few selectively retrievable sections "
            f"({len(sections)}; minimum {MIN_SECTIONS})"
        )

    missing = sorted(REQUIRED_SECTIONS - section_names)
    if missing:
        errors.append(f"{slug}: missing required production sections: {missing}")

    entry_sections = list((skill.get("meta") or {}).get("entry_sections") or [])
    if entry_sections != list(ENTRY_SECTIONS):
        errors.append(
            f"{slug}: entry_sections must be exactly {list(ENTRY_SECTIONS)!r} "
            "so core retrieval is predictable"
        )
    for entry in entry_sections:
        if entry not in section_names:
            errors.append(f"{slug}: entry section {entry!r} is not a real level-2 section")

    core, _ = skill_section_content(skill, section="core")
    for entry in entry_sections:
        section_body = str(sections.get(entry) or "")
        if section_body and section_body not in core:
            errors.append(f"{slug}: core retrieval does not preserve complete entry section {entry!r}")
    if "skill core clipped" in core:
        errors.append(f"{slug}: core retrieval contains destructive clipping marker")

    for required in REQUIRED_SECTIONS:
        body = str(sections.get(required) or "").strip()
        if body and len(body) < 180:
            errors.append(
                f"{slug}: required section {required!r} is too shallow "
                f"({len(body)} chars; minimum 180)"
            )


def _check_distinctiveness(parsed: list[dict], errors: list[str]) -> None:
    token_sets = {
        str(skill["slug"]): _body_tokens(str(skill.get("content") or "")) for skill in parsed
    }
    slugs = sorted(token_sets)
    for index, left in enumerate(slugs):
        for right in slugs[index + 1 :]:
            union = token_sets[left] | token_sets[right]
            if not union:
                continue
            score = len(token_sets[left] & token_sets[right]) / len(union)
            if score >= BODY_OVERLAP_ERROR:
                errors.append(
                    f"{left}/{right}: bundled skill bodies are suspiciously similar "
                    f"(Jaccard {score:.3f} >= {BODY_OVERLAP_ERROR:.2f})"
                )


def run_gate(root: Path = ROOT) -> dict:
    skills_root = root / "src" / "ai_layer" / "builtin_skills"
    parsed: list[dict] = []
    errors: list[str] = []
    for path in sorted(skills_root.glob("*.md")):
        skill = _parse_skill_text(
            slug=path.stem, text=path.read_text(encoding="utf-8"), path=str(path)
        )
        parsed.append(skill)

    validation = validate_native_catalog(parsed)
    for issue in validation.get("issues", []):
        errors.append(f"{issue.get('slug')}: {issue.get('problem')}")

    for skill in parsed:
        slug = skill["slug"]
        meta = skill.get("meta") or {}
        if meta.get("slug") != slug:
            errors.append(f"{slug}: frontmatter slug must match file name")
        if meta.get("kind") not in VALID_KINDS:
            errors.append(f"{slug}: invalid kind")
        present_obsolete = sorted(OBSOLETE_ROUTING_KEYS & set(meta))
        if present_obsolete:
            errors.append(
                f"{slug}: obsolete AI Layer runtime routing metadata present: {present_obsolete}"
            )

        sections = list(skill_sections(skill))
        if not sections:
            errors.append(f"{slug}: at least one selectively retrievable section is required")
        else:
            for section in sections:
                content, _ = skill_section_content(skill, section=section)
                if not str(content or "").strip():
                    errors.append(f"{slug}: section {section!r} is empty")

        _check_depth(skill, errors)

        try:
            native = render_native_skill(skill)
        except Exception as exc:  # gate should report every invalid skill in one pass
            errors.append(f"{slug}: native skill render failed: {exc}")
        else:
            canonical = str(skill.get("content") or "").strip()
            if canonical not in native:
                errors.append(f"{slug}: native activation does not contain the complete canonical body")
            if not native.startswith("---\nname: "):
                errors.append(f"{slug}: native activation lacks host-compatible routing frontmatter")
            if "description:" not in native.split("---\n", 2)[1]:
                errors.append(f"{slug}: native activation frontmatter lacks routing description")

    _check_distinctiveness(parsed, errors)

    return {
        "ok": not errors,
        "skills": len(parsed),
        "errors": errors,
        "quality_floor": {
            "min_content_chars": MIN_CONTENT_CHARS,
            "min_content_words": MIN_CONTENT_WORDS,
            "min_sections": MIN_SECTIONS,
            "required_sections": sorted(REQUIRED_SECTIONS),
            "max_body_overlap_jaccard": BODY_OVERLAP_ERROR,
        },
        "native_catalog": validation,
        "routing_owner": "host-native",
        "activation_payload": "full-authoritative-skill",
        "automatic_domain_skill_injection": False,
    }


if __name__ == "__main__":
    result = run_gate()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
