from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_runtime_home() -> Path:
    xdg = os.getenv("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "ai-layer"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LAYER_", extra="ignore")

    database_url: str = "postgresql+psycopg://ai_layer:ai_layer@127.0.0.1:54329/ai_layer"
    home: Path = Path.home() / ".ai-layer"
    runtime_home: Path = _default_runtime_home()
    embedding_provider: str = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimensions: int = 384
    scan_max_file_bytes: int = 524_288
    scan_max_files: int = 10_000

    @property
    def skills_dir(self) -> Path:
        return self.home / "skills"

    @property
    def project_skills_dir(self) -> Path:
        # Project-scoped skills are machine state, not repository files. This keeps both standard
        # and strict-private projects free of AI Layer skill artifacts while preserving durable
        # project identity through the registry project_id.
        return self.home / "project-skills"

    @property
    def skill_registry_file(self) -> Path:
        return self.home / "skill-registry.json"

    @property
    def skill_imports_dir(self) -> Path:
        return self.home / "skill-imports"

    @property
    def skill_inbox_dir(self) -> Path:
        return self.home / "skill-inbox"

    @property
    def skill_packages_dir(self) -> Path:
        # Large skill assets (references/data/scripts) live in machine state, never in project repos
        # and never enter model context unless the selected skill explicitly asks for them.
        return self.home / "skill-packages"

    @property
    def policies_dir(self) -> Path:
        return self.home / "policies"

    @property
    def config_file(self) -> Path:
        return self.home / "config.yaml"

    @property
    def install_state_file(self) -> Path:
        return self.home / "install.json"

    @property
    def projects_registry_file(self) -> Path:
        return self.home / "projects.json"

    @property
    def projects_state_dir(self) -> Path:
        return self.home / "projects"

    @property
    def machine_runtime_dir(self) -> Path:
        return self.home / "runtime"

    @property
    def stable_bin_dir(self) -> Path:
        return self.runtime_home / "current" / "bin"

    @property
    def stable_mcp_executable(self) -> Path:
        override = os.getenv("AI_LAYER_MCP_EXECUTABLE")
        return Path(override).expanduser() if override else self.stable_bin_dir / "ai-layer-mcp"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
