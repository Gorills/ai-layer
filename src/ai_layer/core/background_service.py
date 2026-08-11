from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_layer import __version__
from ai_layer.core.config import get_settings

SERVICE_UNIT = "ai-layer.service"
SERVICE_MARKER = "# Managed by Local AI Development Layer"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_PROCESS_STARTED_MONOTONIC = time.monotonic()
_PROCESS_STARTED_AT = datetime.now(UTC).isoformat()


def service_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def service_runtime_payload() -> dict[str, Any]:
    mode = os.getenv("AI_LAYER_SERVICE_MODE", "manual").strip().lower() or "manual"
    return {
        "mode": mode,
        "background": mode == "background",
        "pid": os.getpid(),
        "started_at": _PROCESS_STARTED_AT,
        "uptime_seconds": round(max(0.0, time.monotonic() - _PROCESS_STARTED_MONOTONIC), 1),
    }


def probe_service(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = 0.4,
) -> dict[str, Any]:
    url = service_url(host, port) + "/health/live"
    try:
        # The caller only supplies a validated loopback host from AI Layer constants/CLI.
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or not payload.get("ok")
            or payload.get("version") != __version__
            or not isinstance(payload.get("service"), dict)
        ):
            return {
                "running": False,
                "url": service_url(host, port),
                "error": "port is not serving the current AI Layer service",
            }
        return {
            "running": True,
            "url": service_url(host, port),
            "version": payload.get("version"),
            "service": payload.get("service") or {},
            "database": payload.get("database"),
            "runtime": payload.get("runtime") or {},
        }
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        return {"running": False, "url": service_url(host, port), "error": str(exc)}


def wait_for_service(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = 3.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, timeout)
    last = probe_service(host, port)
    while not last.get("running") and time.monotonic() < deadline:
        time.sleep(0.1)
        last = probe_service(host, port)
    return last


def _systemd_user_dir() -> Path:
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "systemd" / "user"


def systemd_unit_path() -> Path:
    return _systemd_user_dir() / SERVICE_UNIT


def _escape_systemd_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _unit_content() -> str:
    settings = get_settings()
    executable = settings.stable_bin_dir / "ai-layer"
    return "\n".join(
        [
            SERVICE_MARKER,
            "[Unit]",
            "Description=Local AI Development Layer Service",
            "",
            "[Service]",
            "Type=simple",
            "EnvironmentFile=-%h/.config/ai-layer/service.env",
            f'Environment="AI_LAYER_HOME={_escape_systemd_value(str(settings.home))}"',
            (
                'Environment="AI_LAYER_RUNTIME_HOME='
                f'{_escape_systemd_value(str(settings.runtime_home))}"'
            ),
            'Environment="AI_LAYER_SERVICE_MODE=background"',
            (
                f'ExecStart="{_escape_systemd_value(str(executable))}" service run '
                f"--host {DEFAULT_HOST} --port {DEFAULT_PORT}"
            ),
            "Restart=always",
            "RestartSec=1",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def _unit_owned(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return SERVICE_MARKER in content or (
        "Description=Local AI Development Layer Service" in content
        and " service run --host 127.0.0.1 --port 8765" in content
    )


def _run_systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    command = ["systemctl", "--user", *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 127, stdout="", stderr=str(exc))


def systemd_user_available() -> bool:
    if platform.system() != "Linux":
        return False
    try:
        result = _run_systemctl("show-environment")
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def install_user_service(*, start: bool = True) -> dict[str, Any]:
    if platform.system() != "Linux":
        return {
            "ok": False,
            "supported": False,
            "reason": "systemd user autostart is supported on Linux only",
        }
    if not systemd_user_available():
        return {
            "ok": False,
            "supported": False,
            "reason": "systemd --user is unavailable in this session",
        }

    executable = get_settings().stable_bin_dir / "ai-layer"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return {
            "ok": False,
            "supported": True,
            "reason": "stable AI Layer launcher is missing; install the release with ./install.sh",
            "executable": str(executable),
        }

    path = systemd_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if not _unit_owned(path):
            return {
                "ok": False,
                "supported": True,
                "unit": str(path),
                "reason": "existing ai-layer.service is not owned by Local AI Development Layer and was left untouched",
            }
    content = _unit_content()
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else None
    except (OSError, UnicodeDecodeError):
        current = None
    if current != content:
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o644)

    reload_result = _run_systemctl("daemon-reload")
    if reload_result.returncode != 0:
        return {
            "ok": False,
            "supported": True,
            "unit": str(path),
            "error": reload_result.stderr.strip(),
        }

    enable_result = _run_systemctl("enable", SERVICE_UNIT)
    if enable_result.returncode != 0:
        return {
            "ok": False,
            "supported": True,
            "unit": str(path),
            "error": enable_result.stderr.strip(),
        }

    if start:
        # restart is intentional on upgrade: a previously running service must load the new release.
        start_result = _run_systemctl("restart", SERVICE_UNIT)
        if start_result.returncode != 0:
            return {
                "ok": False,
                "supported": True,
                "unit": str(path),
                "error": start_result.stderr.strip(),
            }
        health = wait_for_service()
    else:
        health = probe_service()

    background_running = bool(
        health.get("running") and (health.get("service") or {}).get("background")
    )
    return {
        "ok": background_running if start else True,
        "supported": True,
        "unit": str(path),
        "enabled": True,
        "running": background_running if start else bool(health.get("running")),
        "url": service_url(),
        "version": health.get("version"),
        **(
            {"error": health.get("error") or "AI Layer port is not owned by the background service"}
            if start and not background_running
            else {}
        ),
    }


def start_user_service() -> dict[str, Any]:
    path = systemd_unit_path()
    if not path.exists():
        return install_user_service(start=True)
    if not _unit_owned(path):
        return {
            "ok": False,
            "supported": True,
            "reason": "existing ai-layer.service is not AI Layer-owned",
        }
    if not systemd_user_available():
        return {
            "ok": False,
            "supported": False,
            "reason": "systemd --user is unavailable in this session",
        }
    current = probe_service()
    if current.get("running") and (current.get("service") or {}).get("background"):
        return {"ok": True, "supported": True, **current}

    # Restart instead of a no-op `start` so an active process from an older release is refreshed.
    result = _run_systemctl("restart", SERVICE_UNIT)
    if result.returncode != 0:
        return {"ok": False, "supported": True, "error": result.stderr.strip()}
    health = wait_for_service()
    background_running = bool(
        health.get("running") and (health.get("service") or {}).get("background")
    )
    return {"ok": background_running, "supported": True, **health}


def restart_user_service() -> dict[str, Any]:
    path = systemd_unit_path()
    if not path.exists():
        return install_user_service(start=True)
    if not _unit_owned(path):
        return {
            "ok": False,
            "supported": True,
            "reason": "existing ai-layer.service is not AI Layer-owned",
        }
    if not systemd_user_available():
        return {
            "ok": False,
            "supported": False,
            "reason": "systemd --user is unavailable in this session",
        }
    result = _run_systemctl("restart", SERVICE_UNIT)
    if result.returncode != 0:
        return {"ok": False, "supported": True, "error": result.stderr.strip()}
    health = wait_for_service()
    background_running = bool(
        health.get("running") and (health.get("service") or {}).get("background")
    )
    return {"ok": background_running, "supported": True, **health}


def stop_user_service() -> dict[str, Any]:
    path = systemd_unit_path()
    if path.exists() and not _unit_owned(path):
        return {
            "ok": False,
            "supported": True,
            "reason": "existing ai-layer.service is not AI Layer-owned",
        }
    if not systemd_user_available():
        return {
            "ok": False,
            "supported": False,
            "reason": "systemd --user is unavailable in this session",
        }
    result = _run_systemctl("stop", SERVICE_UNIT)
    if result.returncode != 0:
        return {"ok": False, "supported": True, "error": result.stderr.strip()}
    return {"ok": True, "supported": True, "running": False, "unit": str(systemd_unit_path())}


def uninstall_user_service() -> dict[str, Any]:
    path = systemd_unit_path()
    if (path.exists() or path.is_symlink()) and not _unit_owned(path):
        return {
            "ok": False,
            "supported": systemd_user_available(),
            "removed": None,
            "errors": ["existing ai-layer.service is not AI Layer-owned and was left untouched"],
        }
    supported = systemd_user_available()
    errors: list[str] = []
    if supported:
        for args in (("disable", "--now", SERVICE_UNIT), ("daemon-reload",)):
            result = _run_systemctl(*args)
            if result.returncode != 0 and args[0] != "disable":
                errors.append(result.stderr.strip())
    path.unlink(missing_ok=True)
    if supported:
        _run_systemctl("daemon-reload")
    return {"ok": not errors, "supported": supported, "removed": str(path), "errors": errors}


def service_status() -> dict[str, Any]:
    health = probe_service()
    payload: dict[str, Any] = {
        "ok": True,
        "running": bool(health.get("running")),
        "url": service_url(),
        "version": health.get("version"),
        "runtime": health.get("service") or {},
        "core_runtime": health.get("runtime") or {},
        "autostart": {
            "supported": False,
            "installed": systemd_unit_path().exists(),
            "owned": _unit_owned(systemd_unit_path()),
            "enabled": False,
        },
    }
    if platform.system() == "Linux" and systemd_user_available():
        enabled = _run_systemctl("is-enabled", SERVICE_UNIT)
        active = _run_systemctl("is-active", SERVICE_UNIT)
        payload["autostart"] = {
            "supported": True,
            "installed": systemd_unit_path().exists(),
            "owned": _unit_owned(systemd_unit_path()),
            "enabled": enabled.returncode == 0 and enabled.stdout.strip() == "enabled",
            "active": active.returncode == 0 and active.stdout.strip() == "active",
            "unit": str(systemd_unit_path()),
        }
    if not health.get("running") and health.get("error"):
        payload["probe_error"] = health["error"]
    return payload
