from __future__ import annotations

# Compatibility facade only: behavior lives in focused Task modules.
# ruff: noqa: F401
from ai_layer.tasks import state_store as _state_store
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
from ai_layer.tasks.lifecycle import adopt_task, cancel_task, create_task, resume_task
from ai_layer.tasks.lifecycle import delegate_current_stage as _delegate_current_stage
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
from ai_layer.workspace import repository as _workspace_repository

_atomic_write_json = _state_store.atomic_write_json
_baseline_path = _state_store.baseline_path
_load_baseline = _state_store.load_baseline
_load_stage_start = _state_store.load_stage_start
_memory_hash_seed = _state_store.memory_hash_seed
_read_json = _state_store.read_json
_stage_start_path = _state_store.stage_start_path
task_key = _state_store.task_key
_task_lock = _state_store.task_lock
_task_root = _state_store.task_root
_task_work_dir = _state_store.task_work_dir
_utc_iso = _state_store.utc_iso
_write_stage_start = _state_store.write_stage_start

capture_repository_state = _workspace_repository.capture_repository_state
repository_changes = _workspace_repository.repository_changes
_git_changed_line_count = _workspace_repository.git_changed_line_count
_git_changed_paths = _workspace_repository.git_changed_paths
_git_visible_paths = _workspace_repository.git_visible_paths
_hash_file = _workspace_repository.hash_file
_repository_files = _workspace_repository.repository_files


def delegate_current_stage(db, project, **kwargs):
    """Compatibility no-op when an older host delegates a workflow-v3 inline MICRO stage."""
    state = current_task(db, project, include_history=False)
    task = dict(state.get("task") or {}) if state.get("active") else {}
    if (task.get("active_stage") or {}).get("execution_mode") == "inline_micro":
        task["delegation_skipped_inline_micro"] = True
        task["delegation_compatibility"] = (
            "This MICRO stage is already authorized inline; do not spawn a worker. Follow next_action."
        )
        return task
    return _delegate_current_stage(db, project, **kwargs)
