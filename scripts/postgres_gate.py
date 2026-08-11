#!/usr/bin/env python3
"""Real-PostgreSQL migration, recovery and concurrency gate for pre-Epics invariants."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def _run(argv: list[str], *, database_url: str) -> dict:
    env = os.environ.copy()
    env["AI_LAYER_DATABASE_URL"] = database_url
    env["AI_LAYER_TEST_POSTGRES_URL"] = database_url
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(argv, cwd=ROOT, env=env, text=True, capture_output=True)
    return {
        "argv": argv,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output": (proc.stdout + proc.stderr)[-8000:],
    }


def _database_url(base_url: str, database: str) -> str:
    return make_url(base_url).set(database=database).render_as_string(hide_password=False)


def _create_database(base_url: str, database: str) -> None:
    admin_url = _database_url(base_url, "postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        engine.dispose()


def _drop_database(base_url: str, database: str) -> None:
    admin_url = _database_url(base_url, "postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"), {"name": database})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
    finally:
        engine.dispose()


def main() -> int:
    base_url = os.getenv("AI_LAYER_TEST_POSTGRES_URL", "").strip()
    if not base_url:
        print(json.dumps({"ok": False, "error": "AI_LAYER_TEST_POSTGRES_URL is required"}))
        return 2

    fresh_name = f"ai_layer_fresh_{uuid4().hex[:12]}"
    upgrade_name = f"ai_layer_upgrade_{uuid4().hex[:12]}"
    results: list[dict] = []
    try:
        _create_database(base_url, fresh_name)
        _create_database(base_url, upgrade_name)
        fresh_url = _database_url(base_url, fresh_name)
        upgrade_url = _database_url(base_url, upgrade_name)

        steps = [
            ("fresh-upgrade-head", [sys.executable, "-m", "alembic", "upgrade", "head"], fresh_url),
            (
                "supported-source-upgrade-0011",
                [sys.executable, "-m", "alembic", "upgrade", "0011_pre_epics_foundation"],
                upgrade_url,
            ),
            ("supported-source-upgrade-head", [sys.executable, "-m", "alembic", "upgrade", "head"], upgrade_url),
            (
                "postgres-integration",
                [sys.executable, "-m", "pytest", "-m", "postgres", "tests/test_postgres_hardening.py"],
                fresh_url,
            ),
        ]
        for name, argv, url in steps:
            result = _run(argv, database_url=url)
            result["name"] = name
            results.append(result)
            if not result["ok"]:
                break
    except Exception as exc:
        results.append({"name": "gate-infrastructure", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        for database in (fresh_name, upgrade_name):
            try:
                _drop_database(base_url, database)
            except Exception as exc:
                results.append({"name": f"cleanup-{database}", "ok": False, "error": f"{type(exc).__name__}: {exc}"})

    required = {
        "fresh-upgrade-head",
        "supported-source-upgrade-0011",
        "supported-source-upgrade-head",
        "postgres-integration",
    }
    passed = {item.get("name") for item in results if item.get("ok")}
    payload = {"ok": required.issubset(passed) and all(item.get("ok") for item in results), "steps": results}
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
