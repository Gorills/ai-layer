from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ai_layer.core.config import get_settings
from ai_layer.core.redaction import (
    bound_text,
    redact_secret_argv,
    redact_secret_env,
    redact_text_with_secrets,
    secret_values_from_argv,
)
from ai_layer.db.models import Project, TaskStage, VerificationRun
from ai_layer.domain.verification import (
    VerificationAssurance,
    VerificationRequest,
    VerificationResult,
)

MAX_STORED_OUTPUT_CHARS = 2_000
_TRUNCATION_MARKER = "\n...[verification output truncated]...\n"
SAFE_ENV_KEYS = {
    "CI",
    "LANG",
    "LC_ALL",
    "PYTHONHASHSEED",
    "PYTHONPATH",
    "NODE_ENV",
    "RUST_BACKTRACE",
}


def _safe_cwd(project_root: Path, relative_cwd: str) -> Path:
    candidate = (project_root / relative_cwd).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("verification cwd must stay inside the registered project root") from exc
    if not candidate.is_dir():
        raise ValueError(f"verification cwd does not exist or is not a directory: {relative_cwd}")
    return candidate


def _environment(overrides: dict[str, str] | None) -> tuple[dict[str, str], dict[str, str]]:
    env = os.environ.copy()
    recorded: dict[str, str] = {}
    for key, value in (overrides or {}).items():
        key = str(key)
        if key not in SAFE_ENV_KEYS and not key.startswith("AI_LAYER_VERIFY_"):
            raise ValueError(
                f"verification environment override `{key}` is not allowlisted; use AI_LAYER_VERIFY_* for task-local non-secret values"
            )
        text = str(value)
        if len(text) > 2_000:
            raise ValueError(f"verification environment override `{key}` is too large")
        env[key] = text
        recorded[key] = text
    return env, recorded


def _summary(stdout: str, stderr: str, extra_secrets: list[str]) -> str:
    stdout = redact_text_with_secrets(stdout, extra_secrets)
    stderr = redact_text_with_secrets(stderr, extra_secrets)
    text = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part).strip()
    return bound_text(text, MAX_STORED_OUTPUT_CHARS, marker=_TRUNCATION_MARKER)


def _write_evidence(project_id: str, payload: dict) -> str:
    root = get_settings().projects_state_dir / project_id / "verification"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{payload['id']}.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    return str(path)


def _execute_verification(
    *, project_id: str, project_root: str | Path, request: VerificationRequest
) -> tuple[VerificationResult, dict]:
    project_root = Path(project_root).resolve()
    cwd = _safe_cwd(project_root, request.cwd)
    env, recorded_env = _environment(request.environment)
    started = datetime.now(UTC)
    exit_code: int | None = None
    timed_out = False
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.run(
            list(request.command),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=request.timeout_seconds,
            check=False,
        )
        exit_code = int(proc.returncode)
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else str(exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else str(exc.stderr or "")
        )
    except OSError as exc:
        exit_code = 127
        stderr = f"{type(exc).__name__}: {exc}"
    completed = datetime.now(UTC)
    run_id = str(uuid.uuid4())
    extra_secrets = secret_values_from_argv(request.command)
    summary = _summary(stdout, stderr, extra_secrets)
    safe_command = redact_secret_argv(request.command)
    safe_env = redact_secret_env(recorded_env)
    payload = {
        "schema": 1,
        "id": run_id,
        "security_boundary": "trusted-local-process-not-sandboxed",
        "required_capability": request.required_capability.value,
        "assurance": VerificationAssurance.AI_LAYER_VERIFIED.value,
        "command": safe_command,
        "cwd": str(cwd),
        "environment": safe_env,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output_summary": summary,
    }
    evidence_ref = _write_evidence(str(project_id), payload)
    result = VerificationResult(
        assurance=VerificationAssurance.AI_LAYER_VERIFIED,
        command=tuple(safe_command),
        cwd=str(cwd),
        started_at=started,
        completed_at=completed,
        exit_code=exit_code,
        timed_out=timed_out,
        output_summary=summary,
        evidence_ref=evidence_ref,
        environment=safe_env,
    )
    return result, {**payload, "evidence_ref": evidence_ref}


class SubprocessVerificationExecutor:
    """Trusted-local subprocess adapter; deliberately not a sandbox."""

    def execute(
        self,
        *,
        project_id,
        project_root: str,
        request: VerificationRequest,
    ) -> tuple[VerificationResult, dict]:
        return _execute_verification(
            project_id=str(project_id),
            project_root=project_root,
            request=request,
        )


def execute_verification(
    project: Project, request: VerificationRequest
) -> tuple[VerificationResult, dict]:
    """Compatibility facade for existing local callers."""
    return SubprocessVerificationExecutor().execute(
        project_id=project.id,
        project_root=project.root_path,
        request=request,
    )


def persist_verification(
    db: Session,
    project: Project,
    result: VerificationResult,
    *,
    stage: TaskStage | None = None,
) -> VerificationRun:
    row = VerificationRun(
        project_id=project.id,
        task_id=stage.task_id if stage is not None else None,
        stage_id=stage.id if stage is not None else None,
        assurance=result.assurance.value,
        command=list(result.command),
        cwd=result.cwd,
        environment=result.environment or {},
        started_at=result.started_at,
        completed_at=result.completed_at,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        output_summary=result.output_summary,
        evidence_ref=result.evidence_ref or "",
    )
    db.add(row)
    db.flush()
    return row
