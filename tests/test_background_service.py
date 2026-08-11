from pathlib import Path
from types import SimpleNamespace

import ai_layer.core.background_service as background


def test_systemd_unit_uses_stable_runtime_and_no_database_secret(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        home=tmp_path / "state",
        runtime_home=tmp_path / "runtime",
        stable_bin_dir=tmp_path / "runtime" / "current" / "bin",
    )
    monkeypatch.setattr(background, "get_settings", lambda: settings)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))

    text = background._unit_content()

    assert str(settings.stable_bin_dir / "ai-layer") in text
    assert "service run --host 127.0.0.1 --port 8765" in text
    assert "AI_LAYER_SERVICE_MODE=background" in text
    assert "AI_LAYER_DATABASE_URL" not in text
    assert "EnvironmentFile=-%h/.config/ai-layer/service.env" in text
    assert "Restart=always" in text
    assert "RestartSec=1" in text
    assert background.SERVICE_MARKER in text


def test_install_user_service_restarts_existing_unit_on_upgrade(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        home=tmp_path / "state",
        runtime_home=tmp_path / "runtime",
        stable_bin_dir=tmp_path / "runtime" / "current" / "bin",
    )
    settings.stable_bin_dir.mkdir(parents=True, exist_ok=True)
    (settings.stable_bin_dir / "ai-layer").write_text("#!/bin/sh\n", encoding="utf-8")
    (settings.stable_bin_dir / "ai-layer").chmod(0o700)
    monkeypatch.setattr(background, "get_settings", lambda: settings)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(background.platform, "system", lambda: "Linux")
    monkeypatch.setattr(background, "systemd_user_available", lambda: True)
    calls = []

    def fake_systemctl(*args):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(background, "_run_systemctl", fake_systemctl)
    monkeypatch.setattr(
        background,
        "wait_for_service",
        lambda *args, **kwargs: {
            "running": True,
            "version": "test",
            "service": {"background": True},
        },
    )

    result = background.install_user_service(start=True)

    assert result["ok"] is True
    assert ("daemon-reload",) in calls
    assert ("enable", background.SERVICE_UNIT) in calls
    assert ("restart", background.SERVICE_UNIT) in calls
    assert Path(result["unit"]).exists()


def test_service_status_keeps_http_liveness_separate_from_autostart(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(background, "probe_service", lambda: {
        "running": True,
        "version": "0.6.0",
        "service": {"background": True, "pid": 123},
    })
    monkeypatch.setattr(background.platform, "system", lambda: "Linux")
    monkeypatch.setattr(background, "systemd_user_available", lambda: False)

    result = background.service_status()

    assert result["running"] is True
    assert result["runtime"]["background"] is True
    assert result["autostart"]["supported"] is False


def test_install_user_service_rejects_manual_process_on_same_port(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        home=tmp_path / "state",
        runtime_home=tmp_path / "runtime",
        stable_bin_dir=tmp_path / "runtime" / "current" / "bin",
    )
    settings.stable_bin_dir.mkdir(parents=True, exist_ok=True)
    (settings.stable_bin_dir / "ai-layer").write_text("#!/bin/sh\n", encoding="utf-8")
    (settings.stable_bin_dir / "ai-layer").chmod(0o700)
    monkeypatch.setattr(background, "get_settings", lambda: settings)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(background.platform, "system", lambda: "Linux")
    monkeypatch.setattr(background, "systemd_user_available", lambda: True)
    monkeypatch.setattr(
        background,
        "_run_systemctl",
        lambda *args: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        background,
        "wait_for_service",
        lambda *args, **kwargs: {
            "running": True,
            "version": "0.6.0",
            "service": {"background": False},
        },
    )

    result = background.install_user_service(start=True)

    assert result["ok"] is False
    assert result["running"] is False
    assert "background service" in result["error"]


def test_install_user_service_requires_stable_launcher(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        home=tmp_path / "state",
        runtime_home=tmp_path / "runtime",
        stable_bin_dir=tmp_path / "runtime" / "current" / "bin",
    )
    monkeypatch.setattr(background, "get_settings", lambda: settings)
    monkeypatch.setattr(background.platform, "system", lambda: "Linux")
    monkeypatch.setattr(background, "systemd_user_available", lambda: True)

    result = background.install_user_service(start=True)

    assert result["ok"] is False
    assert result["supported"] is True
    assert "stable AI Layer launcher is missing" in result["reason"]


def test_service_management_refuses_unowned_or_symlinked_unit(monkeypatch, tmp_path: Path):
    settings = SimpleNamespace(
        home=tmp_path / "state",
        runtime_home=tmp_path / "runtime",
        stable_bin_dir=tmp_path / "runtime" / "current" / "bin",
    )
    settings.stable_bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = settings.stable_bin_dir / "ai-layer"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o700)
    monkeypatch.setattr(background, "get_settings", lambda: settings)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(background.platform, "system", lambda: "Linux")
    monkeypatch.setattr(background, "systemd_user_available", lambda: True)

    unit = background.systemd_unit_path()
    unit.parent.mkdir(parents=True)
    unit.write_text("[Unit]\nDescription=User service\n", encoding="utf-8")
    result = background.install_user_service(start=False)
    assert result["ok"] is False
    assert "left untouched" in result["reason"]
    assert "User service" in unit.read_text(encoding="utf-8")

    unit.unlink()
    outside = tmp_path / "outside.service"
    outside.write_text("DO NOT TOUCH\n", encoding="utf-8")
    unit.symlink_to(outside)
    result = background.install_user_service(start=False)
    assert result["ok"] is False
    assert outside.read_text(encoding="utf-8") == "DO NOT TOUCH\n"
