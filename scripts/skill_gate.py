#!/usr/bin/env python3
"""Executable native-first contract gate for every bundled production skill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_layer.skills.native import render_native_descriptor, validate_native_catalog  # noqa: E402
from ai_layer.skills.service import _parse_skill_text, skill_section_content, skill_sections  # noqa: E402

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


def run_gate(root: Path = ROOT) -> dict:
    skills_root = root / "src" / "ai_layer" / "builtin_skills"
    parsed: list[dict] = []
    errors: list[str] = []
    for path in sorted(skills_root.glob("*.md")):
        skill = _parse_skill_text(slug=path.stem, text=path.read_text(encoding="utf-8"), path=str(path))
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
            errors.append(f"{slug}: obsolete AI Layer runtime routing metadata present: {present_obsolete}")

        sections = list(skill_sections(skill))
        if not sections:
            errors.append(f"{slug}: at least one selectively retrievable section is required")
        else:
            for section in sections:
                content = skill_section_content(skill, section=section)
                if not str(content or "").strip():
                    errors.append(f"{slug}: section {section!r} is empty")

        try:
            descriptor = render_native_descriptor(skill)
        except Exception as exc:  # gate should report every invalid skill in one pass
            errors.append(f"{slug}: native descriptor render failed: {exc}")
        else:
            if "skill_get(" not in descriptor:
                errors.append(f"{slug}: native descriptor does not direct targeted authoritative retrieval")
            if 'section="full"` only' not in descriptor:
                errors.append(f"{slug}: native descriptor does not make full retrieval exceptional")

    return {
        "ok": not errors,
        "skills": len(parsed),
        "errors": errors,
        "native_catalog": validation,
        "routing_owner": "host-native",
        "automatic_domain_skill_injection": False,
    }


if __name__ == "__main__":
    result = run_gate()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
