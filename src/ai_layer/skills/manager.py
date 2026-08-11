from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Iterable
from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.filelock import directory_lock
from ai_layer.skills.common import (
    _atomic_json,
    _atomic_write,
    _sha_bytes,
    _utcnow,
    builtin_skill_dir,
)
from ai_layer.skills.common import (
    skill_import_dir as _import_dir,
)
from ai_layer.skills.constants import (
    MAX_ARCHIVE_BYTES,
    SAFE_SOURCE_TYPES,
    VALID_SCOPES,
)
from ai_layer.skills.contracts import (
    normalize_skill_text,
    validate_skill_text,
)
from ai_layer.skills.registry import (
    _project_identity,
    _record_key,
    _registry_lock,
    _skill_target,
    _write_registry,
    find_skill_record,
    load_skill_registry,
)
from ai_layer.skills.sources import (
    _catalog_source,
)
from ai_layer.skills.sources import (
    read_url as _read_url_impl,
)
from ai_layer.skills.packages import (
    _decode_document,
    _package_files_for_doc,
    _package_risk_issues,
    _source_documents,
)


def _read_url(url: str) -> bytes:
    # Kept as a manager-level seam so tests/hosts can replace network I/O without patching internals.
    return _read_url_impl(url, max_bytes=MAX_ARCHIVE_BYTES)


def import_skills(
    source: str | None = None,
    *,
    content: str | None = None,
    scope: str = "global",
    project_root: str | Path | None = None,
    slug: str | None = None,
    description: str | None = None,
    task_terms: Iterable[str] | None = None,
    always: bool = False,
    source_member: str | None = None,
    source_type_override: str | None = None,
) -> list[dict]:
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported skill scope: {scope}")
    canonical_root: str | None = None
    project_id: str | None = None
    if scope == "project":
        if project_root is None:
            raise ValueError("project_root is required for project-scoped skill imports")
        canonical_root, project_id = _project_identity(project_root)
    source_type, source_label, docs, source_files = _source_documents(source, content=content)
    if source_type == "catalog" and not source_member and source:
        catalog = _catalog_source(str(source))
        if catalog is not None:
            source_member = catalog[1].get("source_member")
    if source_member:
        wanted = source_member.strip().replace("\\", "/").lstrip("/")
        matches = [item for item in docs if item[0] == wanted or item[0].endswith("/" + wanted)]
        if len(matches) != 1:
            available = [name for name, _ in docs[:40]]
            raise ValueError(
                f"source_member must resolve to exactly one skill document; matches={len(matches)} available={available}"
            )
        docs = matches
    if source_type_override:
        if source_type_override not in SAFE_SOURCE_TYPES:
            raise ValueError(f"Unsupported skill source type: {source_type_override}")
        source_type = source_type_override
    if slug and len(docs) != 1:
        raise ValueError("Explicit slug can only be used when importing one skill document")

    previews: list[dict] = []
    for index, (name, data) in enumerate(docs):
        raw_text = _decode_document(name, data)
        normalized, _, metadata_origin = normalize_skill_text(
            raw_text,
            slug=slug if index == 0 else None,
            description=description if index == 0 else None,
            task_terms=task_terms,
            always=always,
        )
        validation = validate_skill_text(normalized)
        validation["metadata_origin"] = metadata_origin
        package_files = _package_files_for_doc(source_files, name)
        package_files["SKILL.md"] = normalized.encode("utf-8")
        package_issues = _package_risk_issues(package_files)
        if package_issues:
            validation["issues"] = list(validation["issues"]) + package_issues
            validation["risk"] = "high"
        package_bytes = sum(len(value) for value in package_files.values())
        package_digest = hashlib.sha256()
        for package_name in sorted(package_files):
            package_digest.update(package_name.encode("utf-8"))
            package_digest.update(b"\0")
            package_digest.update(package_files[package_name])
            package_digest.update(b"\0")
        import_id = str(uuid.uuid4())
        meta = {
            "import_id": import_id,
            "slug": validation["slug"],
            "scope": scope,
            "project_root": canonical_root,
            "project_id": project_id,
            "source_type": source_type,
            "source": source_label,
            "source_member": name,
            "source_sha256": _sha_bytes(data),
            "normalized_sha256": validation["sha256"],
            "metadata_origin": validation["metadata_origin"],
            "risk": validation["risk"],
            "issues": validation["issues"],
            "package_files": len(package_files),
            "package_bytes": package_bytes,
            "package_sha256": package_digest.hexdigest(),
            "created_at": _utcnow(),
            "compatibility_warnings": (
                [
                    "always=true is compatibility-only; native hosts own skill activation. Put truly always-on policy in host Rules."
                ]
                if always
                else []
            ),
        }
        base = _import_dir() / import_id
        _atomic_write(base.with_suffix(".md"), normalized.encode("utf-8"))
        package_stage = base.with_suffix(".assets")
        if package_stage.exists():
            import shutil

            shutil.rmtree(package_stage)
        for package_name, package_data in package_files.items():
            _atomic_write(package_stage / package_name, package_data)
        _atomic_json(base.with_suffix(".json"), meta)
        previews.append(
            {
                **meta,
                "description": validation["description"],
                "kind": validation["kind"],
                "keywords": validation["meta"].get("keywords", []),
                "entry_sections": validation["meta"].get("entry_sections", []),
                "sections": validation["sections"],
            }
        )
    slugs = [str(item["slug"]) for item in previews]
    duplicates = sorted({item for item in slugs if slugs.count(item) > 1})
    if duplicates:
        for item in previews:
            for suffix in (".json", ".md"):
                (_import_dir() / item["import_id"]).with_suffix(suffix).unlink(missing_ok=True)
            import shutil

            shutil.rmtree(
                (_import_dir() / item["import_id"]).with_suffix(".assets"), ignore_errors=True
            )
        raise ValueError(f"Skill source resolves to duplicate slugs: {duplicates}")
    return previews


def _load_import(import_id: str) -> tuple[dict, str]:
    if not re.fullmatch(r"[0-9a-f-]{36}", import_id):
        raise ValueError("Invalid skill import id")
    base = _import_dir() / import_id
    meta_path = base.with_suffix(".json")
    text_path = base.with_suffix(".md")
    if not meta_path.exists() or not text_path.exists():
        raise FileNotFoundError(f"Unknown/expired skill import: {import_id}")
    if meta_path.is_symlink() or text_path.is_symlink():
        raise RuntimeError("Refusing symlinked skill import state")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    text = text_path.read_text(encoding="utf-8")
    return meta, text


def _builtin_slugs() -> set[str]:
    return {
        item.name.removesuffix(".md")
        for item in builtin_skill_dir().iterdir()
        if item.name.endswith(".md")
    }


def _package_target(*, scope: str, slug: str, project_id: str | None) -> Path:
    base = get_settings().skill_packages_dir
    if base.is_symlink():
        raise RuntimeError(f"Refusing symlinked skill package root: {base}")
    owner = "global" if scope == "global" else f"project/{project_id}"
    target = base / owner / slug
    if target.is_symlink():
        raise RuntimeError(f"Refusing symlinked skill package target: {target}")
    return target


def _install_package_assets(
    import_id: str, *, scope: str, slug: str, project_id: str | None, normalized_text: str
) -> tuple[Path | None, int, int]:
    import shutil

    stage = (_import_dir() / import_id).with_suffix(".assets")
    if not stage.exists():
        return None, 0, 0
    target = _package_target(scope=scope, slug=slug, project_id=project_id)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True, exist_ok=False)
    try:
        files = 0
        size = 0
        for item in sorted(stage.rglob("*")):
            if item.is_symlink():
                raise RuntimeError(f"Refusing symlinked staged skill asset: {item}")
            if not item.is_file():
                continue
            rel = item.relative_to(stage)
            payload = item.read_bytes()
            _atomic_write(temp / rel, payload)
            files += 1
            size += len(payload)
        _atomic_write(temp / "SKILL.md", normalized_text.encode("utf-8"))
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.with_name(f".{target.name}.old")
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            os.replace(target, backup)
        os.replace(temp, target)
        if backup.exists():
            shutil.rmtree(backup)
        return target, files, size
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


def install_import(
    import_id: str,
    *,
    approve: bool,
    replace: bool = False,
    allow_high_risk: bool = False,
    project_root: str | Path | None = None,
) -> dict:
    meta, text = _load_import(import_id)
    validation = validate_skill_text(text)
    if validation["sha256"] != meta.get("normalized_sha256"):
        raise RuntimeError("Skill import content changed after validation; re-import it")
    if not approve:
        raise RuntimeError(
            "Skill import is quarantined. Explicit approval is required before installation."
        )
    if validation["risk"] == "high" and not allow_high_risk:
        raise RuntimeError(
            "High-risk skill requires explicit allow_high_risk approval after reviewing validation issues."
        )

    scope = str(meta["scope"])
    slug = str(meta["slug"])
    if slug in _builtin_slugs():
        raise RuntimeError(
            f"Refusing imported skill collision with managed built-in `{slug}`. Use a distinct slug for project/global specialization."
        )

    from ai_layer.skills.native import validate_routing_description

    routing_issues = validate_routing_description(slug, str(validation.get("description") or ""))
    if routing_issues:
        raise RuntimeError(
            "Skill native routing description failed validation before installation: "
            + "; ".join(routing_issues)
        )

    effective_project_root = project_root
    if scope == "project":
        stored_root = str(meta.get("project_root") or "")
        if effective_project_root is None:
            effective_project_root = stored_root
        root, project_id = _project_identity(effective_project_root)
        if project_id != str(meta.get("project_id")) or root != stored_root:
            raise RuntimeError(
                "Project-scoped skill import identity no longer matches the target project"
            )
    else:
        project_id = None
        root = None

    from ai_layer.skills.native import assert_native_targets_available

    assert_native_targets_available(slug, scope=scope, project_root=effective_project_root)
    target, _, _ = _skill_target(scope=scope, slug=slug, project_root=effective_project_root)
    if target.is_symlink():
        raise RuntimeError(f"Refusing symlinked skill target: {target}")

    with directory_lock(_registry_lock()):
        registry = load_skill_registry()
        existing = next(
            (
                x
                for x in registry["skills"]
                if isinstance(x, dict) and _record_key(x) == (scope, project_id, slug)
            ),
            None,
        )
        if existing is not None and not replace:
            raise RuntimeError(
                f"Skill `{slug}` is already installed in {scope} scope; pass replace=True to update it."
            )
        if target.exists() and existing is None:
            raise RuntimeError(
                f"Skill target already exists but is not registry-managed: {target}. "
                "AI Layer will not overwrite unmanaged custom skill files, even with replace=True."
            )
        # Install package assets first so a package-validation/copy failure cannot leave
        # an unmanaged context-bearing skill file behind. The package directory itself
        # is replaced atomically by _install_package_assets().
        package_root, package_files, package_bytes = _install_package_assets(
            import_id, scope=scope, slug=slug, project_id=project_id, normalized_text=text
        )
        try:
            _atomic_write(target, text.encode("utf-8"))
        except Exception:
            # New installs can be rolled back completely. For replacements the previous
            # registry record remains authoritative; avoid deleting a pre-existing package.
            if existing is None and package_root is not None:
                import shutil

                shutil.rmtree(package_root, ignore_errors=True)
            raise
        record = {
            "slug": slug,
            "scope": scope,
            "project_id": project_id,
            "project_root": root,
            "status": "enabled",
            "trust": "approved",
            "risk": validation["risk"],
            "version": str(validation["meta"].get("version") or ""),
            "source_type": meta.get("source_type"),
            "source": meta.get("source"),
            "source_member": meta.get("source_member"),
            "source_sha256": meta.get("source_sha256"),
            "installed_sha256": validation["sha256"],
            "metadata_origin": meta.get("metadata_origin"),
            "package_root": str(package_root) if package_root else None,
            "package_files": package_files,
            "package_bytes": package_bytes,
            "package_sha256": meta.get("package_sha256"),
            "installed_at": existing.get("installed_at") if existing else _utcnow(),
            "updated_at": _utcnow(),
        }
        registry["skills"] = [
            x
            for x in registry["skills"]
            if not (isinstance(x, dict) and _record_key(x) == (scope, project_id, slug))
        ]
        registry["skills"].append(record)
        _write_registry(registry)
    for suffix in (".json", ".md"):
        (_import_dir() / import_id).with_suffix(suffix).unlink(missing_ok=True)
    import shutil

    shutil.rmtree((_import_dir() / import_id).with_suffix(".assets"), ignore_errors=True)
    from ai_layer.skills.native import sync_native_after_skill_change

    native_sync = sync_native_after_skill_change(scope=scope, project_root=effective_project_root)
    return {
        **record,
        "path": str(target),
        "sections": validation["sections"],
        "issues": validation["issues"],
        "compatibility_warnings": list(meta.get("compatibility_warnings") or []),
        "native_sync": native_sync,
    }


def create_project_skill(
    project_root: str | Path,
    *,
    slug: str,
    content: str,
    description: str | None = None,
    task_terms: Iterable[str] | None = None,
    always: bool = False,
    replace: bool = False,
) -> dict:
    previews = import_skills(
        content=content,
        scope="project",
        project_root=project_root,
        slug=slug,
        description=description,
        task_terms=task_terms,
        always=always,
        source_type_override="agent-authored",
    )
    preview = previews[0]
    if preview["risk"] == "high":
        raise RuntimeError(f"Refusing high-risk agent-authored skill `{slug}`: {preview['issues']}")
    return install_import(
        preview["import_id"], approve=True, replace=replace, project_root=project_root
    )


def set_skill_enabled(
    slug: str, *, scope: str, enabled: bool, project_root: str | Path | None = None
) -> dict:
    target, root, project_id = _skill_target(scope=scope, slug=slug, project_root=project_root)
    if enabled:
        from ai_layer.skills.native import assert_native_targets_available

        assert_native_targets_available(slug, scope=scope, project_root=project_root)
    with directory_lock(_registry_lock()):
        registry = load_skill_registry()
        record = next(
            (
                x
                for x in registry["skills"]
                if isinstance(x, dict) and _record_key(x) == (scope, project_id, slug)
            ),
            None,
        )
        if record is None:
            raise RuntimeError(f"Skill `{slug}` is not registry-managed in {scope} scope")
        if not target.exists():
            raise RuntimeError(f"Managed skill file is missing: {target}")
        record["status"] = "enabled" if enabled else "disabled"
        record["updated_at"] = _utcnow()
        _write_registry(registry)
        result = {**record, "project_root": root, "path": str(target)}
    from ai_layer.skills.native import sync_native_after_skill_change

    result["native_sync"] = sync_native_after_skill_change(scope=scope, project_root=project_root)
    return result


def remove_skill(slug: str, *, scope: str, project_root: str | Path | None = None) -> dict:
    target, root, project_id = _skill_target(scope=scope, slug=slug, project_root=project_root)
    with directory_lock(_registry_lock()):
        registry = load_skill_registry()
        record = next(
            (
                x
                for x in registry["skills"]
                if isinstance(x, dict) and _record_key(x) == (scope, project_id, slug)
            ),
            None,
        )
        if record is None:
            raise RuntimeError(f"Skill `{slug}` is not registry-managed in {scope} scope")
        if target.is_symlink():
            raise RuntimeError(f"Refusing symlinked skill target: {target}")
        target.unlink(missing_ok=True)
        import shutil

        shutil.rmtree(
            _package_target(scope=scope, slug=slug, project_id=project_id), ignore_errors=True
        )
        registry["skills"] = [
            x
            for x in registry["skills"]
            if not (isinstance(x, dict) and _record_key(x) == (scope, project_id, slug))
        ]
        _write_registry(registry)
    from ai_layer.skills.native import sync_native_after_skill_change

    native_sync = sync_native_after_skill_change(scope=scope, project_root=project_root)
    return {
        "slug": slug,
        "scope": scope,
        "project_root": root,
        "removed": True,
        "native_sync": native_sync,
    }


def skill_manager_info(slug: str, *, project_root: str | Path | None = None) -> dict | None:
    # Project-specific match has priority for explicit info, but collisions with built-ins are forbidden on install.
    if project_root is not None:
        record = find_skill_record(slug, scope="project", project_root=project_root)
        if record:
            return record
    for record in load_skill_registry().get("skills", []):
        if (
            isinstance(record, dict)
            and record.get("scope") == "global"
            and record.get("slug") == slug
        ):
            return dict(record)
    return None


def update_skill(
    slug: str, *, scope: str, project_root: str | Path | None = None, allow_high_risk: bool = False
) -> dict:
    record = find_skill_record(slug, scope=scope, project_root=project_root)
    if record is None:
        raise RuntimeError(f"Skill `{slug}` is not registry-managed in {scope} scope")
    source = str(record.get("source") or "")
    source_type = str(record.get("source_type") or "")
    if source_type not in {"local-file", "url", "catalog"} or not source:
        raise RuntimeError("This skill has no refreshable source; re-import it explicitly.")
    previews = import_skills(
        source,
        scope=scope,
        project_root=project_root,
        slug=slug,
        source_member=record.get("source_member"),
    )
    if len(previews) != 1:
        raise RuntimeError("Refresh source no longer resolves to exactly one skill")
    return install_import(
        previews[0]["import_id"],
        approve=True,
        replace=True,
        allow_high_risk=allow_high_risk,
        project_root=project_root,
    )


def inbox_sources() -> list[Path]:
    path = get_settings().skill_inbox_dir
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked skill inbox: {path}")
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return [
        item
        for item in sorted(path.iterdir())
        if not item.name.startswith(".")
        and (item.is_dir() or item.suffix.casefold() in {".md", ".zip"})
    ]
