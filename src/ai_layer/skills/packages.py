from __future__ import annotations

import os
import re
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

from ai_layer.skills.constants import (
    ALLOWED_PACKAGE_NAMES, ALLOWED_PACKAGE_SUFFIXES, HIGH_RISK_PATTERNS, MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_EXPANDED_BYTES, MAX_ARCHIVE_FILES, MAX_ARCHIVE_MEMBER_BYTES, MAX_SKILL_BYTES,
    MEDIUM_RISK_PATTERNS, PACKAGE_SCRIPT_HIGH_RISK_PATTERNS,
)
from ai_layer.skills.contracts import _frontmatter
from ai_layer.skills.sources import _catalog_source, _normalize_remote_skill_url, _validate_url, read_url as _read_url_impl

def _read_url(url: str) -> bytes:
    return _read_url_impl(url, max_bytes=MAX_ARCHIVE_BYTES)

def _safe_package_name(name: str) -> bool:
    path = PurePosixPath(name)
    return path.name.casefold() in ALLOWED_PACKAGE_NAMES or path.suffix.casefold() in ALLOWED_PACKAGE_SUFFIXES


def _normalized_archive_path(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe path in skill archive: {name}")
    cleaned = "/".join(part for part in path.parts if part not in {"", "."})
    if not cleaned:
        raise ValueError(f"Unsafe empty path in skill archive: {name}")
    return cleaned


def _read_zip_members(archive: zipfile.ZipFile) -> tuple[dict[str, bytes], list[tuple[str, str]], int]:
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_FILES:
        raise ValueError("Skill archive contains too many files")
    regular: dict[str, bytes] = {}
    symlinks: list[tuple[str, str]] = []
    expanded = 0
    for info in members:
        if info.is_dir():
            continue
        name = _normalized_archive_path(info.filename)
        if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            raise ValueError(f"Skill archive member too large: {info.filename}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raw_target = archive.read(info)
            if len(raw_target) > 4096:
                raise ValueError(f"Symlink target is too large: {info.filename}")
            try:
                target = raw_target.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise ValueError(f"Invalid symlink target in skill archive: {info.filename}") from exc
            if not target or target.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", target):
                raise ValueError(f"Unsafe symlink target in skill archive: {info.filename} -> {target}")
            symlinks.append((name, target))
            continue
        if not _safe_package_name(name):
            continue
        payload = archive.read(info)
        expanded += len(payload)
        if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ValueError("Expanded skill archive exceeds safety budget")
        regular[name] = payload
    return regular, symlinks, expanded


def _resolved_link_target(link_name: str, raw_target: str) -> str:
    target_path = PurePosixPath(link_name).parent.joinpath(PurePosixPath(raw_target))
    parts: list[str] = []
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"Skill archive symlink escapes source: {link_name} -> {raw_target}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ValueError(f"Invalid skill archive symlink: {link_name} -> {raw_target}")
    return "/".join(parts)


def _add_materialized(regular: dict[str, bytes], name: str, payload: bytes, expanded: int) -> int:
    if not _safe_package_name(name):
        return expanded
    next_expanded = expanded + len(payload)
    if next_expanded > MAX_ARCHIVE_EXPANDED_BYTES:
        raise ValueError("Expanded skill archive exceeds safety budget after symlink materialization")
    if name not in regular and len(regular) + 1 > MAX_ARCHIVE_FILES:
        raise ValueError("Skill archive expands to too many package files")
    regular[name] = payload
    return next_expanded


def _materialize_links(regular: dict[str, bytes], symlinks: list[tuple[str, str]], expanded: int) -> int:
    for link_name, raw_target in symlinks:
        target = _resolved_link_target(link_name, raw_target)
        if target in regular:
            expanded = _add_materialized(regular, link_name, regular[target], expanded)
            continue
        prefix = target.rstrip("/") + "/"
        matches = [(name, payload) for name, payload in list(regular.items()) if name.startswith(prefix)]
        if not matches:
            raise ValueError(f"Unresolved skill archive symlink: {link_name} -> {raw_target}")
        for name, payload in matches:
            virtual = f"{link_name.rstrip('/')}/{name[len(prefix):]}"
            expanded = _add_materialized(regular, virtual, payload, expanded)
    return expanded


def _safe_zip_files(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("Skill archive is too large")
    temp = tempfile.SpooledTemporaryFile(max_size=MAX_ARCHIVE_BYTES + 1)
    temp.write(data)
    temp.seek(0)
    with zipfile.ZipFile(temp) as archive:
        regular, symlinks, expanded = _read_zip_members(archive)
    _materialize_links(regular, symlinks, expanded)
    return regular


def _skill_docs(files: dict[str, bytes]) -> list[tuple[str, bytes]]:
    markdown = [(name, data) for name, data in files.items() if PurePosixPath(name).suffix.casefold() == ".md"]
    native = [item for item in markdown if PurePosixPath(item[0]).name.casefold() == "skill.md"]
    result = native or markdown
    if not result:
        raise ValueError("No Markdown skill files found in source")
    return sorted(result, key=lambda item: item[0])


def _read_local_package_files(source_root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    seen_real: set[tuple[str, str]] = set()
    total = 0

    def add_file(virtual: Path, real: Path) -> None:
        nonlocal total
        try:
            resolved = real.resolve(strict=True)
            resolved.relative_to(source_root.resolve())
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Skill package path escapes source root: {real}") from exc
        if not _safe_package_name(virtual.as_posix()):
            return
        size = resolved.stat().st_size
        if size > MAX_ARCHIVE_MEMBER_BYTES:
            raise ValueError(f"Skill package member too large: {virtual}")
        payload = resolved.read_bytes()
        total += len(payload)
        if total > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ValueError("Expanded skill package exceeds safety budget")
        files[virtual.as_posix()] = payload

    def walk(virtual_dir: Path, real_dir: Path) -> None:
        key = (virtual_dir.as_posix(), str(real_dir.resolve()))
        if key in seen_real:
            return
        seen_real.add(key)
        for child in sorted(real_dir.iterdir(), key=lambda item: item.name):
            virtual = virtual_dir / child.name
            if child.is_symlink():
                resolved = child.resolve(strict=True)
                try:
                    resolved.relative_to(source_root.resolve())
                except ValueError as exc:
                    raise RuntimeError(f"Symlinked skill source escapes import root: {child} -> {resolved}") from exc
                if resolved.is_dir():
                    walk(virtual, resolved)
                elif resolved.is_file():
                    add_file(virtual, resolved)
                continue
            if child.is_dir():
                walk(virtual, child)
            elif child.is_file():
                add_file(virtual, child)
            if len(files) > MAX_ARCHIVE_FILES:
                raise ValueError("Skill directory contains too many package files")

    walk(Path("."), source_root)
    return {name.removeprefix("./"): payload for name, payload in files.items()}


def _source_documents(source: str | None, *, content: str | None = None) -> tuple[str, str, list[tuple[str, bytes]], dict[str, bytes]]:
    if content is not None:
        payload = content.encode("utf-8")
        return "inline", "inline", [("skill.md", payload)], {"skill.md": payload}
    if source is None or not str(source).strip():
        raise ValueError("skill source or content is required")
    source = str(source).strip()
    if source == "-":
        raise ValueError("stdin source is supported by CLI; MCP callers should pass inline content")
    catalog = _catalog_source(source)
    if catalog is not None:
        _, spec = catalog
        data = _read_url(spec["source"])
        files = _safe_zip_files(data)
        return "catalog", source, _skill_docs(files), files
    if source.startswith("https://"):
        fetch_url = _normalize_remote_skill_url(source)
        data = _read_url(fetch_url)
        if fetch_url.casefold().endswith(".zip") or data[:4] == b"PK\x03\x04":
            files = _safe_zip_files(data)
            return "url", source, _skill_docs(files), files
        name = Path(urllib.parse.urlparse(fetch_url).path).name or "skill.md"
        files = {name: data}
        return "url", source, [(name, data)], files

    raw_path = Path(source).expanduser()
    if raw_path.is_symlink():
        # A user may deliberately point to a package link. Dereference only when it remains inside
        # the selected source parent; otherwise ask for the actual package/repository directory.
        resolved = raw_path.resolve(strict=True)
        try:
            resolved.relative_to(raw_path.parent.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Refusing skill source symlink outside its parent: {raw_path} -> {resolved}") from exc
    path = raw_path.resolve()
    if path.is_file():
        data = path.read_bytes()
        if path.suffix.casefold() == ".zip":
            files = _safe_zip_files(data)
            return "zip", str(path), _skill_docs(files), files
        if path.suffix.casefold() != ".md":
            raise ValueError(f"Unsupported skill file: {path}; expected .md or .zip")
        return "local-file", str(path), [(path.name, data)], {path.name: data}
    if path.is_dir():
        files = _read_local_package_files(path)
        docs = _skill_docs(files)
        return "local-directory", str(path), docs, files
    raise FileNotFoundError(f"Skill source does not exist: {path}")


def _package_files_for_doc(files: dict[str, bytes], doc_name: str) -> dict[str, bytes]:
    doc = PurePosixPath(doc_name)
    parent = "" if str(doc.parent) == "." else doc.parent.as_posix().rstrip("/") + "/"
    selected: dict[str, bytes] = {}
    for name, payload in files.items():
        if parent and not name.startswith(parent):
            continue
        rel = name[len(parent):] if parent else name
        if not rel or rel.startswith("../"):
            continue
        selected[rel] = payload
    return selected


def _package_risk_issues(files: dict[str, bytes]) -> list[dict]:
    issues: list[dict] = []
    for name, payload in files.items():
        if PurePosixPath(name).suffix.casefold() not in {".py", ".js", ".ts"}:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            issues.append({"severity": "high", "reason": f"package script is not UTF-8: {name}"})
            continue
        for pattern, reason in PACKAGE_SCRIPT_HIGH_RISK_PATTERNS:
            if re.search(pattern, text):
                issues.append({"severity": "high", "reason": f"{reason}: {name}"})
    # Keep the preview compact and deterministic.
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in issues:
        key = (item["severity"], item["reason"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:20]


def _decode_document(name: str, data: bytes) -> str:
    if len(data) > MAX_SKILL_BYTES:
        raise ValueError(f"Skill {name} is too large: {len(data)} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Skill {name} must be UTF-8 text") from exc

