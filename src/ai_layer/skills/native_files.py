from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

from ai_layer.core.paths import project_mode
from ai_layer.skills.native_descriptor import native_descriptor_name


def atomic_write_native(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def descriptor_metadata(path: Path) -> dict[str, str] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = re.search(
        r"<!-- AI-LAYER NATIVE SKILL v1 scope=(global|project) project=([^ ]+) canonical=([^ ]+) -->",
        content,
    )
    if not match:
        return None
    return {"scope": match.group(1), "project": match.group(2), "canonical": match.group(3)}


def descriptor_owned(path: Path) -> bool:
    return descriptor_metadata(path) is not None


def sync_native_root(
    root: Path, desired: dict[str, str], *, scope: str, project_key: str = "-"
) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    removed: list[str] = []
    for name, content in desired.items():
        target = root / name / "SKILL.md"
        if target.exists() and not descriptor_owned(target):
            raise RuntimeError(
                f"Native skill ownership conflict: {target} already exists and is not AI Layer-owned."
            )
        atomic_write_native(target, content)
        written.append(str(target))
    for child in root.iterdir():
        descriptor = child / "SKILL.md" if child.is_dir() and not child.is_symlink() else None
        if descriptor is None or child.name in desired:
            continue
        metadata = descriptor_metadata(descriptor)
        if not metadata or metadata.get("scope") != scope or metadata.get("project") != project_key:
            continue
        shutil.rmtree(child)
        removed.append(str(child))
    return {"root": str(root), "written": written, "removed": removed}


def global_native_roots(home: Path | None = None) -> dict[str, Path]:
    home = (home or Path.home()).expanduser()
    return {
        "cursor_codex": home / ".agents" / "skills",
        "antigravity": home / ".gemini" / "config" / "skills",
    }


def remove_legacy_project_bridge(project_root: str | Path) -> list[str]:
    root = Path(project_root).expanduser().resolve()
    removed: list[str] = []
    for target in (
        root / ".cursor" / "skills" / "ai-layer" / "SKILL.md",
        root / ".claude" / "skills" / "ai-layer" / "SKILL.md",
        root / ".agents" / "skills" / "ai-layer" / "SKILL.md",
    ):
        if not target.is_file() or target.is_symlink():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "AI-LAYER OWNED FILE" not in content and "# AI Layer bridge" not in content:
            continue
        parent = target.parent
        target.unlink(missing_ok=True)
        try:
            parent.rmdir()
        except OSError:
            pass
        removed.append(str(target))
    return removed


def remove_project_native_skills(project_root: str | Path, *, home: Path | None = None) -> dict:
    root = Path(project_root).expanduser().resolve()
    project_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    removed: list[str] = []
    locations = [root / ".agents" / "skills", *global_native_roots(home).values()]
    for location in locations:
        if not location.is_dir() or location.is_symlink():
            continue
        for child in list(location.iterdir()):
            target = child / "SKILL.md" if child.is_dir() and not child.is_symlink() else None
            if target is None:
                continue
            metadata = descriptor_metadata(target)
            if (
                not metadata
                or metadata.get("scope") != "project"
                or metadata.get("project") != project_key
            ):
                continue
            shutil.rmtree(child)
            removed.append(str(child))
    return {"project_root": str(root), "removed": removed}


def remove_global_native_skills(*, home: Path | None = None) -> dict:
    removed: list[str] = []
    for location in global_native_roots(home).values():
        if not location.is_dir() or location.is_symlink():
            continue
        for child in list(location.iterdir()):
            target = child / "SKILL.md" if child.is_dir() and not child.is_symlink() else None
            if target is None or not descriptor_owned(target):
                continue
            shutil.rmtree(child)
            removed.append(str(child))
    return {"removed": removed}


def assert_native_targets_available(
    slug: str,
    *,
    scope: str,
    project_root: str | Path | None = None,
    home: Path | None = None,
) -> None:
    if scope == "global":
        names = [(path, slug) for path in global_native_roots(home).values()]
    elif scope == "project":
        if project_root is None:
            raise ValueError("project_root is required for project native skill preflight")
        root = Path(project_root).expanduser().resolve()
        mode = project_mode(root)
        external = mode in {"external", "strict-private"}
        name = native_descriptor_name(slug, project_root=root, external_scope=external)
        names = (
            [(path, name) for path in global_native_roots(home).values()]
            if external
            else [(root / ".agents" / "skills", name)]
        )
    else:
        raise ValueError(f"Unsupported skill scope: {scope}")
    for base, name in names:
        target = base / name / "SKILL.md"
        if target.exists() and not descriptor_owned(target):
            raise RuntimeError(
                f"Native skill ownership conflict: {target} already exists and is not AI Layer-owned."
            )


def native_catalog_files(
    project_root: str | Path, *, home: Path | None = None
) -> dict[str, list[Path]]:
    root = Path(project_root).expanduser().resolve()
    project_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    global_roots = global_native_roots(home)

    def selected(base: Path) -> list[Path]:
        if not base.is_dir() or base.is_symlink():
            return []
        result: list[Path] = []
        for child in sorted(base.iterdir(), key=lambda p: p.name):
            target = child / "SKILL.md" if child.is_dir() and not child.is_symlink() else None
            if target is None:
                continue
            metadata = descriptor_metadata(target)
            if not metadata:
                continue
            if metadata.get("scope") == "global" or (
                metadata.get("scope") == "project" and metadata.get("project") == project_key
            ):
                result.append(target)
        return result

    shared = selected(global_roots["cursor_codex"])
    antigravity = selected(global_roots["antigravity"])
    workspace = selected(root / ".agents" / "skills")
    return {
        "cursor": [*shared, *workspace],
        "codex": [*shared, *workspace],
        "antigravity": [*antigravity, *workspace],
    }
