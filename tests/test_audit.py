from pathlib import Path

from ai_layer.audit.service import audit_path, check_latest_flow, mcp_audit, read_audit
from ai_layer.core.registry import register_project


def test_mcp_audit_records_call_without_argument_values(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "audit-test", project.name)
    with mcp_audit(project, "memory_context", arg_keys=["task", "project_root"]):
        pass

    events = read_audit(project)
    assert len(events) == 1
    event = events[0]
    assert event["tool"] == "memory_context"
    assert event["ok"] is True
    assert event["arg_keys"] == ["project_root", "task"]
    raw = audit_path(project).read_text(encoding="utf-8")
    assert "secret prompt" not in raw
    assert ".ai-layer/audit/mcp.jsonl" in audit_path(project).as_posix()


def test_mcp_audit_records_error_type_and_reraises(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "audit-error", project.name)
    try:
        with mcp_audit(project, "decision_search", arg_keys=["query"]):
            raise ValueError("sensitive details must not be logged")
    except ValueError:
        pass
    event = read_audit(project)[0]
    assert event["ok"] is False
    assert event["error_type"] == "ValueError"
    raw = audit_path(project).read_text(encoding="utf-8")
    assert "sensitive details" not in raw


def test_audit_check_requires_completion_save(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "audit-test", project.name)
    with mcp_audit(project, "project_status", arg_keys=["task"]):
        pass
    failed = check_latest_flow(project)
    assert failed["ok"] is False
    assert failed["session_saved"] is False

    with mcp_audit(project, "knowledge_search", arg_keys=["query"]):
        pass
    with mcp_audit(project, "session_save", arg_keys=["goal", "current_state"]):
        pass
    passed = check_latest_flow(project)
    assert passed["ok"] is True
    assert passed["tools"] == ["memory_context", "knowledge_search", "session_save"]


def test_audit_check_detects_duplicate_memory_context_in_same_flow(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    register_project(project, "audit-test", project.name)
    with mcp_audit(project, "project_status", arg_keys=[]):
        pass
    with mcp_audit(project, "memory_context", arg_keys=["task"]):
        pass
    with mcp_audit(project, "memory_context", arg_keys=["task"]):
        pass
    with mcp_audit(project, "session_save", arg_keys=["goal", "current_state"]):
        pass

    result = check_latest_flow(project)
    assert result["ok"] is True
    assert result["flow_start_tool"] == "project_status"
    assert result["project_status_calls"] == 1
    assert result["memory_context_calls"] == 2
    assert result["memory_context_count_scope"] == "ai_layer_server_audit_events_only"
    assert result["host_tool_schema_discovery_counted"] is False
    assert result["duplicate_memory_context"] is True
    assert result["warnings"] == [
        {
            "code": "tool_economy",
            "message": "legacy memory_context was called 2 times in one completed flow; prefer focused Project Intelligence tools instead of repeating the compatibility payload.",
        }
    ]


def test_audit_event_identifies_server_version_and_pid(tmp_path: Path):
    import os

    from ai_layer import __version__

    register_project(tmp_path, "audit-version", tmp_path.name)
    with mcp_audit(tmp_path, "memory_context", arg_keys=["task"]):
        pass
    event = read_audit(tmp_path)[0]
    assert event["server_version"] == __version__
    assert event["pid"] == os.getpid()


def test_audit_check_fails_when_tool_error_occurs_inside_completed_flow(tmp_path: Path):
    project = tmp_path / "project-error"
    project.mkdir()
    register_project(project, "audit-test", project.name)
    with mcp_audit(project, "project_status", arg_keys=["task"]):
        pass
    try:
        with mcp_audit(project, "decision_search", arg_keys=["query"]):
            raise RuntimeError("provider failed")
    except RuntimeError:
        pass
    with mcp_audit(project, "session_save", arg_keys=["goal", "current_state"]):
        pass

    result = check_latest_flow(project)
    assert result["ok"] is False
    assert result["session_saved"] is True
    assert result["failures"] == [{"tool": "decision_search", "error_type": "RuntimeError"}]


def test_unregistered_global_bootstrap_attempt_does_not_create_state_or_swallow_error(
    tmp_path: Path,
):
    project = tmp_path / "unregistered"
    project.mkdir()
    try:
        with mcp_audit(project, "memory_context", arg_keys=["task"]):
            raise LookupError("not registered")
    except LookupError as exc:
        assert str(exc) == "not registered"
    else:
        raise AssertionError("audit context must preserve tool exceptions")
    assert not audit_path(project).exists()


def test_audit_check_accepts_completed_managed_task_with_automatic_handoff(tmp_path: Path):
    project = tmp_path / "managed-task"
    project.mkdir()
    register_project(project, "audit-managed", project.name)
    with mcp_audit(project, "project_status", arg_keys=["task"]):
        pass
    with mcp_audit(project, "task_create", arg_keys=["goal"]) as state:
        state["metrics"] = {"task": "T-0001", "status": "active", "stage": "implement"}
    with mcp_audit(project, "task_stage_complete", arg_keys=["stage_id"]) as state:
        state["metrics"] = {
            "task": "T-0001",
            "status": "active",
            "next_stage": "review",
            "open_findings": 0,
            "handoff_written": False,
        }
    with mcp_audit(project, "task_stage_complete", arg_keys=["stage_id"]) as state:
        state["metrics"] = {
            "task": "T-0001",
            "status": "completed",
            "next_stage": None,
            "open_findings": 0,
            "handoff_written": True,
        }

    result = check_latest_flow(project)
    assert result["ok"] is True
    assert result["managed_task"] is True
    assert result["terminal_checkpoint"] == "managed_task"
    assert result["session_saved"] is True
    assert result["tools"][-1] == "task_stage_complete"


def test_audit_log_rotates_and_reads_bounded_recent_history(monkeypatch, tmp_path: Path):
    import ai_layer.audit.service as audit

    project = tmp_path / "rotate"
    project.mkdir()
    register_project(project, "audit-rotate", project.name)
    monkeypatch.setattr(audit, "MAX_AUDIT_BYTES", 700)

    for index in range(12):
        with mcp_audit(project, f"tool_{index}", arg_keys=["x"]):
            pass

    current = audit_path(project)
    previous = current.with_name("mcp.previous.jsonl")
    assert current.exists()
    assert previous.exists()
    assert current.stat().st_size < 2 * audit.MAX_AUDIT_BYTES
    assert previous.stat().st_size < 2 * audit.MAX_AUDIT_BYTES
    recent = read_audit(project, limit=4)
    assert len(recent) == 4
    assert recent[-1]["tool"] == "tool_11"


def test_audit_check_accepts_stage_specific_terminal_completion(tmp_path: Path):
    project = tmp_path / "managed-task-specific"
    project.mkdir()
    register_project(project, "audit-managed-specific", project.name)
    with mcp_audit(project, "project_status", arg_keys=["task"]):
        pass
    with mcp_audit(project, "task_create", arg_keys=["goal"]) as state:
        state["metrics"] = {"task": "T-0001", "status": "active", "stage": "implement"}
    with mcp_audit(
        project, "task_implementation_complete", arg_keys=["summary", "checks"]
    ) as state:
        state["metrics"] = {
            "task": "T-0001",
            "status": "active",
            "next_stage": "review",
            "handoff_written": False,
        }
    with mcp_audit(
        project, "task_review_complete", arg_keys=["summary", "checks", "verdict"]
    ) as state:
        state["metrics"] = {
            "task": "T-0001",
            "status": "completed",
            "next_stage": None,
            "handoff_written": True,
        }

    result = check_latest_flow(project)
    assert result["ok"] is True
    assert result["managed_task"] is True
    assert result["terminal_checkpoint"] == "managed_task"
    assert result["session_saved"] is True
    assert result["tools"][-1] == "task_review_complete"
