from pathlib import Path

import pytest

from ai_layer.mcp import context


def setup_function():
    context.reset_project_bindings_for_tests()


def teardown_function():
    context.reset_project_bindings_for_tests()


def test_project_scoped_resolution_never_falls_back_to_process_cwd(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AI_LAYER_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(
        context.ProjectContextRequiredError, match="PROJECT_CONTEXT_REQUIRED"
    ) as exc:
        context.resolve_project_root(None, tool="task_create")
    assert str(tmp_path.resolve()) not in str(exc.value)
    assert "Do not derive it from MCP cwd" in str(exc.value)


def test_successfully_bound_project_is_reused_when_root_is_omitted(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AI_LAYER_PROJECT_ROOT", raising=False)
    project = tmp_path / "food"
    project.mkdir()
    canonical = context.bind_project_root(project)
    assert context.resolve_project_root(None, tool="task_create") == canonical


def test_multiple_bound_projects_make_implicit_resolution_fail_closed(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AI_LAYER_PROJECT_ROOT", raising=False)
    first = tmp_path / "food"
    second = tmp_path / "other"
    first.mkdir()
    second.mkdir()
    context.bind_project_root(first)
    context.bind_project_root(second)
    with pytest.raises(context.ProjectContextRequiredError, match="PROJECT_CONTEXT_AMBIGUOUS"):
        context.resolve_project_root(None, tool="task_current")


def test_project_specific_environment_is_authoritative_even_after_multiple_bindings(
    monkeypatch, tmp_path: Path
):
    first = tmp_path / "food"
    second = tmp_path / "other"
    fixed = tmp_path / "fixed"
    for item in (first, second, fixed):
        item.mkdir()
    context.bind_project_root(first)
    context.bind_project_root(second)
    monkeypatch.setenv("AI_LAYER_PROJECT_ROOT", str(fixed))
    assert context.resolve_project_root(None, tool="task_create") == str(fixed.resolve())


def test_memory_context_binds_exact_root_for_following_task_create(monkeypatch, tmp_path: Path):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from ai_layer.mcp import server
    from ai_layer.mcp.tools import project_context as project_tools
    from ai_layer.mcp.tools import tasks as task_tools

    project_root = tmp_path / "food"
    project_root.mkdir()
    seen = {}

    @contextmanager
    def fake_session_scope():
        yield object()

    @contextmanager
    def fake_audit(*args, **kwargs):
        yield {}

    def fake_get_project(db, root, required=True):
        seen.setdefault("roots", []).append(root)
        context.bind_project_root(root)
        return SimpleNamespace(root_path=root, id="project-1")

    monkeypatch.delenv("AI_LAYER_PROJECT_ROOT", raising=False)
    context.reset_project_bindings_for_tests()
    monkeypatch.setattr(project_tools, "session_scope", fake_session_scope)
    monkeypatch.setattr(task_tools, "session_scope", fake_session_scope)
    monkeypatch.setattr(project_tools, "mcp_audit", fake_audit)
    monkeypatch.setattr(task_tools, "mcp_audit", fake_audit)
    monkeypatch.setattr(project_tools, "_project", fake_get_project)
    monkeypatch.setattr(task_tools, "_project", fake_get_project)
    monkeypatch.setattr(
        project_tools,
        "build_memory_context",
        lambda db, project, task, limit: {
            "task_runtime": {"active": False},
            "memory": [],
            "skills": [],
        },
    )
    monkeypatch.setattr(
        task_tools,
        "db_create_task",
        lambda db, project, goal, acceptance_criteria, constraints, **kwargs: {
            "key": "T-0001",
            "status": "active",
            "active_stage": {"kind": "implement", "id": "stage-1"},
        },
    )

    ctx = server.memory_context(task="Fix food project", project_root=str(project_root))
    assert ctx["project_root"] == str(project_root.resolve())

    created = server.task_create(goal="Fix food project")
    assert created["project_root"] == str(project_root.resolve())
    assert seen["roots"] == [str(project_root.resolve()), str(project_root.resolve())]


def test_task_create_without_explicit_env_or_bound_project_fails_before_cwd(
    monkeypatch, tmp_path: Path
):
    from ai_layer.mcp import server

    monkeypatch.delenv("AI_LAYER_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    context.reset_project_bindings_for_tests()
    with pytest.raises(context.ProjectContextRequiredError, match="PROJECT_CONTEXT_REQUIRED"):
        server.task_create(goal="Must not target MCP cwd")


def test_task_next_and_stage_specific_completion_use_durable_bound_state(
    monkeypatch, tmp_path: Path
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from ai_layer.mcp import server
    from ai_layer.mcp.tools import tasks as task_tools

    project_root = tmp_path / "food"
    project_root.mkdir()
    calls = []

    @contextmanager
    def fake_session_scope():
        yield object()

    @contextmanager
    def fake_audit(*args, **kwargs):
        yield {}

    monkeypatch.delenv("AI_LAYER_PROJECT_ROOT", raising=False)
    context.reset_project_bindings_for_tests()
    context.bind_project_root(project_root)
    monkeypatch.setattr(task_tools, "session_scope", fake_session_scope)
    monkeypatch.setattr(task_tools, "mcp_audit", fake_audit)
    monkeypatch.setattr(
        task_tools, "_project", lambda db, root: SimpleNamespace(root_path=root, id="project-1")
    )
    monkeypatch.setattr(
        task_tools,
        "db_next_task_action",
        lambda db, project: {
            "state": "active",
            "next_action": {
                "action": "record_stage_result",
                "tool": "task_implementation_complete",
            },
            "task": {
                "key": "T-0001",
                "status": "active",
                "active_stage": {"kind": "implement", "worker_id": "impl-1"},
            },
        },
    )
    monkeypatch.setattr(
        task_tools,
        "db_complete_current_stage",
        lambda db, project, **kwargs: (
            calls.append(kwargs)
            or {
                "key": "T-0001",
                "status": "active",
                "active_stage": {"kind": "review", "worker_id": None},
            }
        ),
    )
    monkeypatch.setattr(task_tools, "_compact_open_transition", lambda db, project, result: result)

    nav = server.task_next()
    assert nav["next_action"]["tool"] == "task_implementation_complete"
    result = server.task_implementation_complete(summary="Done", checks=["pytest passed"])
    assert result["active_stage"]["kind"] == "review"
    assert calls == [
        {
            "expected_kind": "implement",
            "summary": "Done",
            "checks": ["pytest passed"],
            "outcome": "done",
            "external_actions": None,
        }
    ]
