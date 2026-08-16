from __future__ import annotations

import pytest

from ai_layer.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_ai_layer_home(monkeypatch, tmp_path):
    """Keep repository tests from mutating the developer's installed ~/.ai-layer state."""
    home = tmp_path / ".ai-layer"
    home.mkdir()
    monkeypatch.setenv("AI_LAYER_HOME", str(home))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
