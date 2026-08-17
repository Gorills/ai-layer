from __future__ import annotations

from pathlib import Path

from ai_layer.integrations.global_install import _install_global_bootstrap_files


def test_supported_host_bootstraps_share_direct_managed_task_route(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    _install_global_bootstrap_files(home)

    artifacts = {
        "codex": home / ".codex" / "AGENTS.md",
        "claude-code": home / ".claude" / "CLAUDE.md",
        "antigravity": home / ".gemini" / "GEMINI.md",
        "cursor": (
            home / ".cursor" / "plugins" / "local" / "ai-layer-bootstrap" / "rules" / "ai-layer.mdc"
        ),
    }

    for host, path in artifacts.items():
        text = path.read_text(encoding="utf-8")
        assert "`project_status`" in text, host
        assert "calls `task_create` directly" in text, host
        assert "creates or links backing Work for managed Tasks automatically" in text, host
        assert "otherwise substantive work" in text, host
        assert "starts with `work_begin`" in text, host
