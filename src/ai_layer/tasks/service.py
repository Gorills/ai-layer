from __future__ import annotations

# This module intentionally re-exports the sequential Task Layer public/compatibility surface.
# Focused owner modules contain the behavior; callers and existing tests import through this facade.
# ruff: noqa: F401
from ai_layer.tasks.completion import complete_current_stage, complete_stage
from ai_layer.tasks.constants import *  # noqa: F403
from ai_layer.tasks.contracts import (
    _bounded_result_data,
    _bounded_text,
    _bounded_text_list,
    _classify_task,
    _configure_stage_agent,
    _contains_any,
    _redact_json_strings,
    _stage_agent_policy,
    _task_text,
)
from ai_layer.tasks.lifecycle import (
    adopt_task,
    cancel_task,
    create_task,
    delegate_current_stage,
    resume_task,
)
from ai_layer.tasks.micro_policy import micro_envelope as _micro_envelope
from ai_layer.tasks.navigation import (
    _blocked_stage_repository_guard,
    _known_completed_terminal_state,
    _latest_resumable_stage,
    _safe_git_changes,
    cleanup_current_review_sandbox,
    next_task_action,
    prepare_current_review_sandbox,
    run_current_review_check,
)
from ai_layer.tasks.review_contracts import (
    _add_findings,
    _apply_verification_results,
    _finding_signature,
    _normalize_external_actions,
    _normalize_findings,
    _normalize_review_submission,
    _normalize_verification_results,
    _open_findings,
)
from ai_layer.tasks.state_store import (
    atomic_write_json as _atomic_write_json,
)
from ai_layer.tasks.state_store import (
    baseline_path as _baseline_path,
)
from ai_layer.tasks.state_store import (
    load_baseline as _load_baseline,
)
from ai_layer.tasks.state_store import (
    load_stage_start as _load_stage_start,
)
from ai_layer.tasks.state_store import (
    memory_hash_seed as _memory_hash_seed,
)
from ai_layer.tasks.state_store import (
    read_json as _read_json,
)
from ai_layer.tasks.state_store import (
    stage_start_path as _stage_start_path,
)
from ai_layer.tasks.state_store import (
    task_key,
)
from ai_layer.tasks.state_store import (
    task_lock as _task_lock,
)
from ai_layer.tasks.state_store import (
    task_root as _task_root,
)
from ai_layer.tasks.state_store import (
    task_work_dir as _task_work_dir,
)
from ai_layer.tasks.state_store import (
    utc_iso as _utc_iso,
)
from ai_layer.tasks.state_store import (
    write_stage_start as _write_stage_start,
)
from ai_layer.tasks.transitions import _complete_task, _privacy_findings
from ai_layer.tasks.views import (
    _active_stage,
    _cleanup_task_review_sandboxes,
    _completion_contract,
    _create_stage,
    _delegation_contract,
    _finding_payload,
    _findings,
    _human_attention_reason,
    _next_action,
    _next_ordinal,
    _persist_task_view,
    _remediation_fix_count,
    _stage_label,
    _stage_payload,
    _stages,
    _validate_worker_id,
    current_task,
    task_to_dict,
)
from ai_layer.tasks.worker_leases import recover_disconnected_worker
from ai_layer.workspace.repository import (
    capture_repository_state,
    repository_changes,
)
from ai_layer.workspace.repository import (
    git_changed_line_count as _git_changed_line_count,
)
from ai_layer.workspace.repository import (
    git_changed_paths as _git_changed_paths,
)
from ai_layer.workspace.repository import (
    git_visible_paths as _git_visible_paths,
)
from ai_layer.workspace.repository import (
    hash_file as _hash_file,
)
from ai_layer.workspace.repository import (
    repository_files as _repository_files,
)

__all__ = [name for name in globals() if not name.startswith("__")]
