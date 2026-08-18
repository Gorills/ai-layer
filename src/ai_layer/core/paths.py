from __future__ import annotations

from pathlib import Path

from ai_layer.core.config import get_settings
from ai_layer.core.registry import get_registered_project


def normalize_root(path: str | Path | None = None) -> Path:
    return Path(path or Path.cwd()).expanduser().resolve()


def _safe_child(base: Path, *parts: str | Path) -> Path:
    relative = Path(*parts)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"Unsafe AI Layer path: {relative}")
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"Refusing AI Layer path redirected by symlink: {current}")
    return current


def project_local_path(root: str | Path, *parts: str | Path) -> Path:
    """Return a lexical path inside a project, rejecting existing symlink components."""
    return _safe_child(Path(root).expanduser().resolve(), *parts)


def project_mode(root: str | Path) -> str:
    item = get_registered_project(root)
    return str(item.get("mode", "standard")) if item else "standard"


def project_provenance(root: str | Path) -> str:
    item = get_registered_project(root)
    return str(item.get("provenance", "allow")) if item else "allow"


def project_meta_dir(root: str | Path) -> Path:
    resolved = Path(root).expanduser().resolve()
    item = get_registered_project(resolved)
    if item:
        project_id = str(item.get("project_id") or "").strip()
        if project_id:
            base = get_settings().home / "projects"
            if base.is_symlink():
                raise RuntimeError(f"Refusing symlinked AI Layer projects state root: {base}")
            base_resolved = base.expanduser().resolve()
            try:
                base_resolved.relative_to(resolved)
            except ValueError:
                pass
            else:
                raise RuntimeError(
                    f"AI Layer machine state must be outside the registered project root: {base_resolved}"
                )
            base.mkdir(parents=True, exist_ok=True)
            return _safe_child(base, project_id)
        if item.get("mode") in {"external", "strict-private"}:
            raise RuntimeError(f"External-state project lacks registry project_id: {resolved}")
    return project_local_path(resolved, ".ai-layer")


def project_state_path(root: str | Path, *parts: str | Path) -> Path:
    return _safe_child(project_meta_dir(root), *parts)


def project_config_path(root: str | Path) -> Path:
    return project_state_path(root, "project.yaml")


def require_initialized(root: Path) -> Path:
    meta = project_meta_dir(root)
    config = project_config_path(root)
    if not config.exists():
        raise RuntimeError(f"Project is not initialized: {root}. Run `ai-layer init` first.")
    return meta
