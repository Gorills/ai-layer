from __future__ import annotations

import hashlib
from pathlib import Path

from ai_layer.core.paths import project_mode
from ai_layer.skills.native_descriptor import (
    NATIVE_DESCRIPTOR_VERSION,
    native_descriptor_name,
    render_native_skill,
    validate_native_catalog,
)
from ai_layer.skills.native_files import global_native_roots, sync_native_root
from ai_layer.skills.service import list_skills


def _publishable_catalog(
    skills: list[dict],
    *,
    project_root: Path | None = None,
    external_scope: bool = False,
) -> tuple[dict[str, str], dict]:
    """Render valid full native activation documents without one legacy skill bricking upgrade.

    New/updated skills are rejected earlier by the manager quality gate. A pre-existing
    invalid skill remains in the canonical store for explicit retrieval but is not
    advertised to host-native routing until its metadata is fixed.
    """
    validation = validate_native_catalog(skills)
    blocked_by_slug: dict[str, list[str]] = {}
    for issue in validation["issues"]:
        slug = str(issue.get("slug") or "")
        blocked_by_slug.setdefault(slug, []).append(
            str(issue.get("problem") or "invalid descriptor")
        )

    desired: dict[str, str] = {}
    published: list[str] = []
    for skill in skills:
        slug = str(skill.get("slug") or "")
        if slug in blocked_by_slug:
            continue
        name = native_descriptor_name(
            slug, project_root=project_root, external_scope=external_scope
        )
        desired[name] = render_native_skill(
            skill,
            project_root=project_root,
            external_scope=external_scope,
        )
        published.append(slug)

    publication = {
        "published": sorted(published),
        "published_count": len(published),
        "blocked": [
            {"slug": slug, "issues": problems} for slug, problems in sorted(blocked_by_slug.items())
        ],
        "blocked_count": len(blocked_by_slug),
    }
    return desired, {**validation, "publication": publication}


def sync_global_native_skills(*, home: Path | None = None) -> dict:
    skills = [skill for skill in list_skills() if skill.get("scope") == "global"]
    desired, validation = _publishable_catalog(skills)
    roots = global_native_roots(home)
    synced = {host: sync_native_root(path, desired, scope="global") for host, path in roots.items()}
    return {
        "descriptor_version": NATIVE_DESCRIPTOR_VERSION,
        "routing_owner": "host-native",
        "activation_payload": "full-authoritative-skill",
        "canonical_skills": len(skills),
        "published_skills": validation["publication"]["published_count"],
        "blocked_skills": validation["publication"]["blocked_count"],
        "validation": validation,
        "hosts": {
            "cursor": {"root": str(roots["cursor_codex"]), "shared_with": "codex"},
            "codex": {"root": str(roots["cursor_codex"]), "shared_with": "cursor"},
            "antigravity": {"root": str(roots["antigravity"])},
        },
        "sync": synced,
    }


def _project_skill_descriptors(
    project_root: Path,
    *,
    external_scope: bool,
) -> tuple[dict[str, str], dict]:
    try:
        skills = [skill for skill in list_skills(project_root) if skill.get("scope") == "project"]
    except RuntimeError as exc:
        if "not registered with durable identity" not in str(exc):
            raise
        skills = []
    return _publishable_catalog(
        skills,
        project_root=project_root,
        external_scope=external_scope,
    )


def sync_project_native_skills(project_root: str | Path, *, home: Path | None = None) -> dict:
    root = Path(project_root).expanduser().resolve()
    mode = project_mode(root)
    project_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    if mode in {"external", "strict-private"}:
        desired, validation = _project_skill_descriptors(root, external_scope=True)
        roots = global_native_roots(home)
        results = {
            host: sync_native_root(path, desired, scope="project", project_key=project_key)
            for host, path in roots.items()
        }
        return {
            "mode": mode,
            "repository_writes": False,
            "scope": "namespaced-global-zero-footprint",
            "descriptors": sorted(desired),
            "activation_payload": "full-authoritative-skill",
            "validation": validation,
            "sync": results,
        }
    desired, validation = _project_skill_descriptors(root, external_scope=False)
    target = root / ".agents" / "skills"
    return {
        "mode": mode,
        "repository_writes": bool(desired),
        "scope": "workspace",
        "descriptors": sorted(desired),
        "activation_payload": "full-authoritative-skill",
        "validation": validation,
        "sync": sync_native_root(target, desired, scope="project", project_key=project_key),
    }


def sync_native_after_skill_change(*, scope: str, project_root: str | Path | None = None) -> dict:
    if scope == "global":
        return sync_global_native_skills()
    if project_root is None:
        raise ValueError("project_root is required for project skill synchronization")
    return sync_project_native_skills(project_root)
