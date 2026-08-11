"""Compatibility facade for repository/workspace helpers.

New repository identity/delta behavior belongs to :mod:`ai_layer.workspace.repository`.
Task-owned durable snapshot paths belong to :mod:`ai_layer.tasks.state_store`.
"""

from ai_layer.tasks.state_store import (
    atomic_write_json as _atomic_write_json,
    baseline_path as _baseline_path,
    load_baseline as _load_baseline,
    load_stage_start as _load_stage_start,
    memory_hash_seed as _memory_hash_seed,
    read_json as _read_json,
    stage_start_path as _stage_start_path,
    task_key,
    task_lock as _task_lock,
    task_root as _task_root,
    task_work_dir as _task_work_dir,
    write_stage_start as _write_stage_start,
)
from ai_layer.workspace.repository import (
    capture_repository_state,
    git_changed_line_count as _git_changed_line_count,
    git_changed_paths as _git_changed_paths,
    git_visible_paths as _git_visible_paths,
    hash_file as _hash_file,
    repository_changes,
    repository_files as _repository_files,
    utc_iso as _utc_iso,
)
from ai_layer.tasks.micro_policy import micro_envelope as _micro_envelope

__all__ = [name for name in globals() if not name.startswith("__")]
