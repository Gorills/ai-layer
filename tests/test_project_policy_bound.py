from __future__ import annotations

import hashlib

from ai_layer.core.config import get_settings
from ai_layer.core.registry import register_project
from ai_layer.policy.project_policy import PROJECT_POLICY_MAX_CHARS, project_policy_snapshot
from ai_layer.policy.service import dynamic_policy, ensure_global_policy

PROJECT_MARKER = "PROJECT_RULE_MUST_SURVIVE"
PRIVACY_MARKER = "Never bypass the privacy guard"


def _strict_private_project(tmp_path, monkeypatch, project_id: str):
    home = tmp_path / "home"
    project = tmp_path / "private"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AI_LAYER_HOME", str(home / ".ai-layer"))
    get_settings.cache_clear()
    register_project(project, project_id, "private", mode="strict-private", provenance="forbid")
    return home, project


def test_project_policy_bound_is_not_raised_to_hide_truncation():
    assert PROJECT_POLICY_MAX_CHARS == 12_000


def test_long_custom_global_prefix_cannot_drop_project_or_privacy_rules(tmp_path, monkeypatch):
    home, project = _strict_private_project(tmp_path, monkeypatch, "t5-global-prefix")
    try:
        global_path = ensure_global_policy()
        global_path.write_text("CUSTOM_GLOBAL_PREFIX " + ("G" * 20_000) + "\n", encoding="utf-8")
        meta = home / ".ai-layer" / "projects" / "t5-global-prefix"
        meta.mkdir(parents=True)
        (meta / "rules.md").write_text(
            f"Always use {PROJECT_MARKER} in this repo.\n", encoding="utf-8"
        )

        full = dynamic_policy(project).strip()
        payload = project_policy_snapshot(project)

        assert PROJECT_MARKER in full
        assert PRIVACY_MARKER in full
        assert len(full) > PROJECT_POLICY_MAX_CHARS
        assert payload["truncated"] is True
        assert payload["chars"] == len(full)
        assert payload["sha256"] == hashlib.sha256(full.encode("utf-8")).hexdigest()
        assert len(payload["text"]) <= PROJECT_POLICY_MAX_CHARS
        assert PROJECT_MARKER in payload["text"]
        assert PRIVACY_MARKER in payload["text"]
        assert "Strict Private Repository Policy" in payload["text"]
        assert "# Project Rules" in payload["text"]
    finally:
        get_settings.cache_clear()


def test_oversized_project_rules_still_keep_strict_private_policy(tmp_path, monkeypatch):
    home, project = _strict_private_project(tmp_path, monkeypatch, "t5-huge-project")
    try:
        meta = home / ".ai-layer" / "projects" / "t5-huge-project"
        meta.mkdir(parents=True)
        (meta / "rules.md").write_text("PROJECT_HEAD " + ("P" * 20_000) + "\n", encoding="utf-8")

        full = dynamic_policy(project).strip()
        payload = project_policy_snapshot(project)

        assert PRIVACY_MARKER in full
        assert payload["truncated"] is True
        assert payload["chars"] == len(full)
        assert payload["sha256"] == hashlib.sha256(full.encode("utf-8")).hexdigest()
        assert len(payload["text"]) <= PROJECT_POLICY_MAX_CHARS
        assert PRIVACY_MARKER in payload["text"]
        assert "Strict Private Repository Policy" in payload["text"]
        assert "# Project Rules" in payload["text"]
    finally:
        get_settings.cache_clear()
