#!/usr/bin/env python3
"""Run the full local gate against an ephemeral checkout-owned PostgreSQL service."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"


def _compose(project: str, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "--file",
        str(COMPOSE_FILE),
        *args,
    ]


def _host_port(output: str) -> int:
    endpoint = output.strip().splitlines()[-1] if output.strip() else ""
    host, separator, port = endpoint.rpartition(":")
    if separator != ":" or host != "127.0.0.1" or not port.isdigit():
        raise RuntimeError(f"unexpected PostgreSQL port mapping: {endpoint!r}")
    value = int(port)
    if not 1 <= value <= 65535:
        raise RuntimeError(f"invalid PostgreSQL host port: {value}")
    return value


def main() -> int:
    checkout = hashlib.sha256(str(ROOT).encode()).hexdigest()[:10]
    project = f"ai-layer-preflight-{checkout}-{uuid4().hex[:8]}"
    compose_env = os.environ.copy()
    compose_env.pop("COMPOSE_FILE", None)
    compose_env.pop("COMPOSE_PROJECT_NAME", None)
    compose_env["AI_LAYER_POSTGRES_PORT"] = "0"

    print(f"[preflight] starting isolated PostgreSQL project {project}", flush=True)
    result = 1
    cleanup_result = 0
    try:
        subprocess.run(
            _compose(project, "up", "-d", "--wait", "postgres"),
            cwd=ROOT,
            env=compose_env,
            check=True,
        )
        mapping = subprocess.run(
            _compose(project, "port", "postgres", "5432"),
            cwd=ROOT,
            env=compose_env,
            check=True,
            capture_output=True,
            text=True,
        )
        port = _host_port(mapping.stdout)
        gate_env = os.environ.copy()
        gate_env["AI_LAYER_TEST_POSTGRES_URL"] = (
            f"postgresql+psycopg://ai_layer:ai_layer@127.0.0.1:{port}/ai_layer"
        )
        completed = subprocess.run(["make", "preflight-ci"], cwd=ROOT, env=gate_env, check=False)
        result = completed.returncode
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"[preflight] ERROR: {exc}", flush=True)
    finally:
        print(f"[preflight] removing isolated PostgreSQL project {project}", flush=True)
        try:
            cleanup = subprocess.run(
                _compose(project, "down", "--volumes", "--remove-orphans"),
                cwd=ROOT,
                env=compose_env,
                check=False,
            )
            cleanup_result = cleanup.returncode
        except OSError as exc:
            cleanup_result = 1
            print(f"[preflight] ERROR: cleanup could not start: {exc}", flush=True)
        if cleanup_result:
            print("[preflight] ERROR: isolated PostgreSQL cleanup failed", flush=True)
    return result or cleanup_result


if __name__ == "__main__":
    raise SystemExit(main())
