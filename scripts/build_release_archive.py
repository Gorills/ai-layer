#!/usr/bin/env python3
"""Build a byte-deterministic install release ZIP from an allowed development repository."""

from __future__ import annotations

import argparse
import hashlib
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (2026, 8, 10, 0, 0, 0)
EXCLUDED_DIRS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_ROOT_ENTRIES = {
    ".coverage",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "venv",
}
# Development repository contents are intentionally broader than an install artifact.
ALLOWED_ROOT_FILES = {
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "GEMINI.md",
    "MAINTAINER_INSTRUCTIONS.md",
    "Makefile",
    "README.md",
    "PROJECT_CHARTER.md",
    "ARCHITECTURE.md",
    "QUALITY_GATES.md",
    "CURRENT_STATE.md",
    "ROADMAP.md",
    "alembic.ini",
    "docker-compose.yml",
    "install.sh",
    "pyproject.toml",
    "uninstall.sh",
}
ALLOWED_ROOT_DIRS = {
    ".github",
    ".githooks",
    "DECISIONS",
    "alembic",
    "dist",
    "docs",
    "release",
    "scripts",
    "src",
    "tests",
}

# Runtime source release intentionally excludes contributor governance/history/tests. The installed
# machine runtime itself is the pinned wheel + migration/runtime assets created by install.sh.
RELEASE_ROOT_FILES = {
    ".env.example",
    "README.md",
    "alembic.ini",
    "docker-compose.yml",
    "install.sh",
    "pyproject.toml",
    "uninstall.sh",
}
RELEASE_ROOT_DIRS = {"alembic", "dist", "release", "scripts", "src"}


def unexpected_top_level_entries(root: Path) -> list[str]:
    allowed = ALLOWED_ROOT_FILES | ALLOWED_ROOT_DIRS | EXCLUDED_ROOT_ENTRIES
    return sorted(path.name for path in root.iterdir() if path.name not in allowed)


def validate_development_tree(root: Path) -> None:
    unexpected = unexpected_top_level_entries(root)
    if unexpected:
        raise RuntimeError(
            "unexpected top-level development repository artifacts: " + ", ".join(unexpected)
        )


def _runtime_candidate(rel: Path) -> bool:
    if len(rel.parts) == 1:
        return rel.name in RELEASE_ROOT_FILES
    return bool(rel.parts and rel.parts[0] in RELEASE_ROOT_DIRS)


def included_files(root: Path) -> list[Path]:
    validate_development_tree(root)
    files: list[Path] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if not _runtime_candidate(rel):
            continue
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] in EXCLUDED_ROOT_ENTRIES:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix in EXCLUDED_SUFFIXES or path.name == ".DS_Store":
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def build(output: Path, root: Path = ROOT) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = root.name
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in included_files(root):
            # Never recursively include the artifact being built when output lives under dist/.
            if path.resolve() == output:
                continue
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{rel}", FIXED_TIME)
            mode = path.stat().st_mode
            perms = 0o755 if mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | perms) << 16
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(
                info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )
    return output


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    built = build(args.output)
    print(f"{built}  sha256={sha256(built)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
