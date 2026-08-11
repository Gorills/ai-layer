from pathlib import Path

from ai_layer.core.config import Settings


def test_project_dotenv_cannot_override_global_runtime_settings(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(
        "AI_LAYER_HOME=/tmp/project-controlled-ai-layer\n"
        "AI_LAYER_DATABASE_URL=postgresql+psycopg://evil/evil\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AI_LAYER_HOME", raising=False)
    monkeypatch.delenv("AI_LAYER_DATABASE_URL", raising=False)
    monkeypatch.chdir(project)

    settings = Settings()
    assert settings.home != Path("/tmp/project-controlled-ai-layer")
    assert settings.database_url != "postgresql+psycopg://evil/evil"


def test_explicit_process_environment_still_overrides_runtime_settings(tmp_path: Path, monkeypatch):
    expected_home = tmp_path / "explicit-home"
    monkeypatch.setenv("AI_LAYER_HOME", str(expected_home))
    settings = Settings()
    assert settings.home == expected_home
