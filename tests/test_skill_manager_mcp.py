import uuid
from contextlib import contextmanager
from types import SimpleNamespace


def test_mcp_project_skill_create_uses_explicit_registered_identity_not_cwd(tmp_path, monkeypatch):
    from ai_layer.core.config import get_settings
    from ai_layer.core.registry import register_project
    from ai_layer.mcp import server
    from ai_layer.mcp.tools import skills as skill_tools

    home = tmp_path / "home"
    project = tmp_path / "repo"
    other = tmp_path / "other-cwd"
    project.mkdir()
    other.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    register_project(project, project_id=str(uuid.uuid4()), name="repo")
    monkeypatch.chdir(other)

    @contextmanager
    def fake_scope():
        yield object()

    monkeypatch.setattr(skill_tools, "session_scope", fake_scope)
    monkeypatch.setattr(skill_tools, "_project", lambda db, root: SimpleNamespace(root_path=root))
    monkeypatch.setattr(skill_tools, "mcp_audit", lambda *args, **kwargs: fake_audit())
    try:
        result = server.skill_project_create(
            slug="ide-project-skill",
            content="# IDE Project Skill\n\n## Core contract\n\nUse the established adapter seam.\n",
            description="Apply when modifying project adapter seams, integration boundaries, or adapter contracts.",
            task_terms=["adapter-seam"],
            project_root=str(project),
        )
        assert result["scope"] == "project"
        assert result["project_root"] == str(project.resolve())
        assert str(other.resolve()) not in result["path"]
        assert not (project / ".ai-layer" / "skills").exists()
    finally:
        get_settings.cache_clear()


@contextmanager
def fake_audit():
    payload = {}
    yield payload
