from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from ai_layer import __version__
from ai_layer.core.config import get_settings
from ai_layer.db.session import database_status, get_engine
from alembic import command

COMMAND_TIMEOUT_SECONDS = 15


def _run_command(
    args: list[str], *, timeout: int = COMMAND_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return subprocess.CompletedProcess(
            args, 124, stdout=stdout, stderr=stderr or "command timed out"
        )
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, stdout="", stderr=str(exc))


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def docker_compose_available() -> tuple[bool, str | None]:
    docker = shutil.which("docker")
    if not docker:
        return False, None
    proc = _run_command([docker, "compose", "version"])
    return proc.returncode == 0, docker


def compose_file() -> Path:
    return get_settings().machine_runtime_dir / "docker-compose.yml"


def _wait_for_database(timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    state = database_status()
    while not state.get("connected") and time.monotonic() < deadline:
        time.sleep(1)
        state = database_status()
    return state


def _container_running(docker: str, name: str) -> tuple[bool | None, str | None]:
    proc = _run_command([docker, "inspect", "-f", "{{.State.Running}}", name])
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    return proc.stdout.strip().lower() == "true", None


def _legacy_container_matches_ai_layer(docker: str, name: str) -> bool:
    proc = _run_command([docker, "inspect", "-f", "{{json .Config.Env}}", name])
    if proc.returncode != 0:
        return False
    try:
        env = set(json.loads(proc.stdout.strip()) or [])
    except json.JSONDecodeError:
        return False
    return "POSTGRES_DB=ai_layer" in env and "POSTGRES_USER=ai_layer" in env


def start_database(timeout: int = 45) -> dict:
    """Ensure the AI Layer database is reachable without destroying legacy v0.1.x state.

    v0.1.0-v0.1.2 compose files used a fixed container name (``ai-layer-postgres``)
    from arbitrary checkout directories. A later release cannot make Compose adopt that
    already-existing container, even though it may be the healthy database we want.

    Therefore readiness is authoritative: if the configured database already answers, use it.
    If the legacy named container exists but is stopped, start it directly. Only create a
    compose-managed container when no usable legacy runtime exists.
    """
    compose = compose_file()

    # Fast path for upgrades: an older AI Layer container may already own the port/data.
    initial = database_status()
    if initial.get("connected"):
        return {
            "ok": True,
            "mode": "already-ready",
            "database": initial,
            "compose": str(compose),
        }

    ok, docker = docker_compose_available()
    if not ok or docker is None:
        return {
            "ok": False,
            "error": "Docker Compose is unavailable and the configured PostgreSQL is not reachable. "
            "Install/start Docker, then rerun `ai-layer upgrade`.",
            "database": initial,
        }
    if not compose.exists():
        return {
            "ok": False,
            "error": (
                f"Runtime compose file is missing: {compose}. "
                "Re-run ./install.sh from the release archive."
            ),
            "database": initial,
        }

    # Backward compatibility: old releases created this exact container name. Do not remove
    # or recreate it because doing so can detach users from the volume that contains memory.
    running, inspect_error = _container_running(docker, "ai-layer-postgres")
    if running is not None:
        if not _legacy_container_matches_ai_layer(docker, "ai-layer-postgres"):
            return {
                "ok": False,
                "mode": "container-name-conflict",
                "error": (
                    "A container named ai-layer-postgres already exists but does not look like "
                    "the AI Layer database. It was left untouched. Rename/remove that unrelated "
                    "container or configure AI_LAYER_DATABASE_URL."
                ),
                "database": database_status(),
            }
        if not running:
            start = _run_command([docker, "start", "ai-layer-postgres"])
            if start.returncode != 0:
                return {
                    "ok": False,
                    "mode": "legacy-container",
                    "error": (start.stderr or start.stdout).strip(),
                    "database": database_status(),
                }
        state = _wait_for_database(timeout)
        if state.get("connected"):
            return {
                "ok": True,
                "mode": "legacy-container",
                "container": "ai-layer-postgres",
                "database": state,
                "compose": str(compose),
            }
        return {
            "ok": False,
            "mode": "legacy-container",
            "error": (
                "Existing ai-layer-postgres container was found, but PostgreSQL did not become "
                "reachable. The container was preserved; inspect it with "
                "`docker logs ai-layer-postgres`."
            ),
            "inspect_error": inspect_error,
            "database": state,
        }

    proc = _run_command(
        [docker, "compose", "-f", str(compose), "up", "-d"],
        timeout=max(COMMAND_TIMEOUT_SECONDS, 45),
    )
    if proc.returncode != 0:
        # A concurrent/legacy startup can race with compose. Re-check the actual dependency
        # before declaring the machine broken.
        state = database_status()
        if state.get("connected"):
            return {
                "ok": True,
                "mode": "ready-after-compose-warning",
                "warning": (proc.stderr or proc.stdout).strip(),
                "database": state,
                "compose": str(compose),
            }
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip(), "database": state}

    state = _wait_for_database(timeout)
    return {
        "ok": bool(state.get("connected")),
        "mode": "compose",
        "database": state,
        "compose": str(compose),
    }


def _alembic_config() -> Config:
    settings = get_settings()
    runtime = settings.machine_runtime_dir
    ini = runtime / "alembic.ini"
    scripts = runtime / "alembic"
    if not ini.exists() or not scripts.exists():
        raise RuntimeError(
            f"Migration runtime is incomplete under {runtime}. Re-run ./install.sh from the release archive."
        )
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(scripts))
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return cfg


def _column_names(inspector, table: str) -> set[str]:
    return {str(column.get("name")) for column in inspector.get_columns(table)}


def _detect_unversioned_revision(inspector, tables: set[str]) -> str:
    """Identify the newest fully materialized pre-Alembic schema without creating new objects.

    Older releases used ``Base.metadata.create_all`` at more than one point in the project's
    lifetime, so an unversioned database can legitimately look like 0001 *or* later revisions.
    Partial revision signatures are refused instead of being guessed.
    """
    required_base = {
        "projects",
        "project_files",
        "knowledge",
        "decisions",
        "sessions",
        "project_skills",
    }
    if not required_base.issubset(tables):
        missing = sorted(required_base - tables)
        raise RuntimeError(
            "Unversioned AI Layer database has an incomplete base schema; refusing to guess a "
            f"migration revision. Missing tables: {', '.join(missing)}"
        )

    session_columns = _column_names(inspector, "sessions")
    evidence = {"verified_facts", "notable_findings"}
    if session_columns & evidence and not evidence.issubset(session_columns):
        raise RuntimeError(
            "Unversioned sessions schema is partially migrated; manual recovery is required."
        )

    project_file_columns = _column_names(inspector, "project_files")
    incremental = {"content_sha256", "mtime_ns", "ctime_ns", "indexed", "scanner_schema"}
    if project_file_columns & incremental and not incremental.issubset(project_file_columns):
        raise RuntimeError(
            "Unversioned project_files schema is partially migrated; manual recovery is required."
        )

    task_tables = {"tasks", "task_stages", "review_findings"}
    if tables & task_tables and not task_tables.issubset(tables):
        raise RuntimeError(
            "Unversioned Task Layer schema is partially migrated; manual recovery is required."
        )
    if task_tables.issubset(tables):
        if not incremental.issubset(project_file_columns) or not evidence.issubset(session_columns):
            raise RuntimeError(
                "Unversioned Task Layer schema is inconsistent with its prerequisite revisions."
            )
        finding_columns = _column_names(inspector, "review_findings")
        hardening = {"verification_evidence", "verification_history", "verified_by_stage_id"}
        if finding_columns & hardening and not hardening.issubset(finding_columns):
            raise RuntimeError(
                "Unversioned review_findings schema is partially hardened; manual recovery is required."
            )
        if hardening.issubset(finding_columns):
            # Historical create_all may have materialized 0006 ORM columns without the raw HNSW
            # index. Stamp 0006 and let later idempotent migration reconciliation ensure auxiliaries.
            return "0006_hardening"
        return "0005_task_execution"
    if incremental.issubset(project_file_columns):
        if not evidence.issubset(session_columns):
            raise RuntimeError(
                "Unversioned incremental schema is inconsistent with session evidence revisions."
            )
        return "0004_incremental_identity"
    if evidence.issubset(session_columns):
        # 0003 differs from 0002 only by persistent server defaults. Inspector default text is
        # dialect-specific, so treat any non-null default on both columns as the 0003 signature.
        defaults = {
            str(column.get("name")): column.get("default")
            for column in inspector.get_columns("sessions")
            if str(column.get("name")) in evidence
        }
        if all(defaults.get(name) is not None for name in evidence):
            return "0003_session_evidence_defaults"
        return "0002_session_evidence"
    return "0001_initial"


def migrate_database() -> dict:
    """Adopt legacy v0.1 schemas once, then use Alembic as the migration source of truth."""
    engine = get_engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    cfg = _alembic_config()
    if "alembic_version" not in tables and "projects" in tables:
        # create_all was used by multiple historical releases. Detect the newest *complete*
        # revision signature already present, stamp exactly that revision, then let Alembic apply
        # only missing migrations. Never run current metadata create_all on an unversioned DB.
        adopted_revision = _detect_unversioned_revision(inspector, tables)
        command.stamp(cfg, adopted_revision)
        command.upgrade(cfg, "head")
        mode = "adopted-unversioned-schema+upgraded"
    else:
        command.upgrade(cfg, "head")
        mode = "upgraded"
    return {"ok": True, "mode": mode}


def write_install_state(extra: dict | None = None) -> dict:
    settings = get_settings()
    payload = {
        "version": __version__,
        "installed_at": _utcnow(),
        "runtime_home": str(settings.runtime_home),
        "mcp_executable": str(settings.stable_mcp_executable),
    }
    if extra:
        payload.update(extra)
    settings.home.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{settings.install_state_file.name}.",
        dir=settings.install_state_file.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, settings.install_state_file)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return payload


def read_install_state() -> dict:
    path = get_settings().install_state_file
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}
