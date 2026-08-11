from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from ai_layer.core.paths import project_state_path
from ai_layer.core.redaction import redact_secrets
from ai_layer.db.models import Project, Task, TaskStage
from ai_layer.tasks.review_workspace import prepare_review_sandbox

MAX_CHECK_TIMEOUT_SECONDS = 900
MAX_OUTPUT_TAIL_CHARS = 6000
MAX_COMMAND_ARGS = 64
MAX_COMMAND_ARG_CHARS = 8_000
MAX_COMMAND_TOTAL_CHARS = 16_000
MAX_EVIDENCE_RECORDS = 100
MAX_EVIDENCE_FILE_BYTES = 512_000
SECRET_ARG_HINTS = (
    "token", "password", "passwd", "secret", "api-key", "api_key", "credential", "authorization",
)
SECRET_ENV_HINTS = (
    "token", "password", "passwd", "secret", "api_key", "apikey", "credential", "authorization",
    "private_key", "access_key", "client_secret",
)
SAFE_ENV_NAMES = {
    "PATH", "LANG", "LANGUAGE", "TERM", "TZ", "TMP", "TEMP", "TMPDIR",
    "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "JAVA_HOME", "GOROOT", "GOPATH",
    "GOMODCACHE", "CARGO_HOME", "RUSTUP_HOME", "NVM_DIR", "PNPM_HOME",
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
}
COMMAND_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?token|token|password|passwd|secret|client[_-]?secret|"
    r"access[_-]?key|private[_-]?key|credential|authorization)[\w.-]*\s*[:=]\s*)([^\s'\";,)}\]]+)"
)

def _is_secret_env_name(name: str) -> bool:
    normalized = name.casefold().replace("-", "_")
    return any(hint in normalized for hint in SECRET_ENV_HINTS)

def _sensitive_values_from_environment(environment: dict[str, str]) -> list[str]:
    values = {
        str(value)
        for key, value in environment.items()
        if _is_secret_env_name(str(key)) and len(str(value)) >= 6
    }
    return sorted(values, key=len, reverse=True)

def _sensitive_values_from_argv(argv: list[str]) -> list[str]:
    values: set[str] = set()
    redact_next = False
    for raw in argv:
        item = str(raw)
        if redact_next:
            if len(item) >= 6:
                values.add(item)
            redact_next = False
            continue
        low = item.casefold()
        if item.startswith("-") and any(hint in low for hint in SECRET_ARG_HINTS):
            if "=" in item:
                _key, value = item.split("=", 1)
                if len(value) >= 6:
                    values.add(value)
            else:
                redact_next = True
        for match in COMMAND_SECRET_ASSIGNMENT_RE.finditer(item):
            value = match.group(2)
            if len(value) >= 6:
                values.add(value)
    return sorted(values, key=len, reverse=True)

def _review_environment(sandbox_root: Path) -> tuple[dict[str, str], list[str]]:
    """Build a minimal execution environment and return host secret values for output scrubbing."""
    host = {str(key): str(value) for key, value in os.environ.items()}
    secrets = _sensitive_values_from_environment(host)
    env: dict[str, str] = {}
    for key, value in host.items():
        if _is_secret_env_name(key):
            continue
        if key in SAFE_ENV_NAMES or key.startswith("LC_"):
            env[key] = value

    runtime_home = sandbox_root / ".ai-layer-runtime-home"
    runtime_tmp = sandbox_root / ".ai-layer-runtime-tmp"
    runtime_home.mkdir(parents=True, exist_ok=True)
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(runtime_home),
            "XDG_CACHE_HOME": str(runtime_home / ".cache"),
            "XDG_CONFIG_HOME": str(runtime_home / ".config"),
            "XDG_DATA_HOME": str(runtime_home / ".local" / "share"),
            "TMPDIR": str(runtime_tmp),
            "TEMP": str(runtime_tmp),
            "TMP": str(runtime_tmp),
            "AI_LAYER_REVIEW_SANDBOX": "1",
        }
    )
    return env, secrets

def _redact_output(value: str, sensitive_values: list[str]) -> str:
    redacted = redact_secrets(value)
    for secret in sensitive_values:
        redacted = redacted.replace(secret, "<redacted>")
    return redacted

def _evidence_path(project: Project, task: Task, stage: TaskStage) -> Path:
    path = project_state_path(
        project.root_path,
        "tasks",
        str(task.id),
        "review-evidence",
        f"{stage.id}.jsonl",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _append_evidence(project: Project, task: Task, stage: TaskStage, payload: dict) -> None:
    path = _evidence_path(project, task, stage)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if path.stat().st_size > MAX_EVIDENCE_FILE_BYTES:
            lines = path.read_text(encoding="utf-8").splitlines()[-MAX_EVIDENCE_RECORDS:]
            path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Evidence append already succeeded. Rotation failure must not turn a completed check into
        # an ambiguous tool failure; the next read remains bounded to the newest records.
        pass
    try:
        path.chmod(0o600)
    except OSError:
        pass

def review_check_evidence(project: Project, task: Task, stage: TaskStage) -> list[dict]:
    path = _evidence_path(project, task, stage)
    if path.is_symlink() or not path.exists():
        return []
    result: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    for line in lines[-50:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result

def latest_review_check_evidence(records: list[dict]) -> list[dict]:
    """Return the latest result per command/cwd so a successful rerun can supersede a failure."""
    latest: dict[tuple[tuple[str, ...], str], dict] = {}
    order: list[tuple[tuple[str, ...], str]] = []
    for item in records:
        key = (
            tuple(str(part) for part in (item.get("command") or [])),
            str(item.get("cwd") or "."),
        )
        if key not in latest:
            order.append(key)
        latest[key] = item
    return [latest[key] for key in order]

def _safe_cwd(root: Path, relative_cwd: str | None) -> Path:
    rel = Path(relative_cwd or ".")
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("review_check_run: cwd must be a relative path inside the review sandbox.")
    candidate = (root / rel).resolve()
    sandbox_root = root.resolve()
    try:
        candidate.relative_to(sandbox_root)
    except ValueError as exc:
        raise ValueError("review_check_run: cwd resolves outside the review sandbox.") from exc
    if not candidate.is_dir():
        raise ValueError(f"review_check_run: cwd does not exist: {rel}")
    return candidate

def _safe_command_for_evidence(argv: list[str]) -> list[str]:
    """Keep check evidence useful without durably storing obvious credential values."""
    safe: list[str] = []
    redact_next = False
    for raw in argv:
        item = str(raw)
        if redact_next:
            safe.append("<redacted>")
            redact_next = False
            continue
        low = item.casefold()
        if item.startswith("-") and any(hint in low for hint in SECRET_ARG_HINTS):
            if "=" in item:
                key, _value = item.split("=", 1)
                safe.append(f"{key}=<redacted>")
            else:
                safe.append(item)
                redact_next = True
            continue
        redacted = redact_secrets(item)
        redacted = COMMAND_SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}<redacted>", redacted
        )
        safe.append(redacted)
    return safe

def run_review_check(
    project: Project,
    task: Task,
    stage: TaskStage,
    *,
    command: list[str],
    relative_cwd: str | None = None,
    timeout_seconds: int = 300,
) -> dict:
    if stage.kind not in {"review", "discovery"} or stage.status != "active":
        raise RuntimeError("review_check_run is available only for an active discovery/review stage.")
    argv = [str(item).strip() for item in command if str(item).strip()]
    if not argv:
        raise ValueError("review_check_run: command must contain at least one argv item.")
    if len(argv) > MAX_COMMAND_ARGS:
        raise ValueError(f"review_check_run: command exceeds the {MAX_COMMAND_ARGS}-argument limit.")
    for index, item in enumerate(argv, start=1):
        if len(item) > MAX_COMMAND_ARG_CHARS:
            raise ValueError(
                f"review_check_run: argv item #{index} exceeds the {MAX_COMMAND_ARG_CHARS}-character limit."
            )
    if sum(len(item) for item in argv) > MAX_COMMAND_TOTAL_CHARS:
        raise ValueError(
            f"review_check_run: command exceeds the {MAX_COMMAND_TOTAL_CHARS}-character total limit."
        )
    timeout = max(1, min(int(timeout_seconds), MAX_CHECK_TIMEOUT_SECONDS))
    sandbox = prepare_review_sandbox(project, task, stage)
    root = Path(sandbox["path"])
    cwd = _safe_cwd(root, relative_cwd)
    canonical = Path(project.root_path).expanduser().resolve()
    for item in argv[1:]:
        pathish = Path(item).expanduser()
        if not pathish.is_absolute():
            continue
        try:
            pathish.resolve().relative_to(canonical)
        except (OSError, ValueError):
            continue
        raise ValueError(
            "review_check_run: command arguments must not point back into the canonical project; "
            "use paths relative to the sandbox cwd."
        )

    started = time.monotonic()
    timed_out = False
    stdout = ""
    stderr = ""
    returncode = 124
    review_env, host_secret_values = _review_environment(root)
    output_secret_values = sorted(
        set(host_secret_values) | set(_sensitive_values_from_argv(argv)),
        key=len,
        reverse=True,
    )
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=review_env,
        )
        returncode = int(proc.returncode)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
    duration_ms = int((time.monotonic() - started) * 1000)
    digest = hashlib.sha256((stdout + "\n" + stderr).encode("utf-8", errors="replace")).hexdigest()
    evidence_id = str(uuid4())
    persisted_record = {
        "evidence_id": evidence_id,
        "stage_id": str(stage.id),
        "command": _safe_command_for_evidence(argv),
        "cwd": str(Path(relative_cwd or ".")),
        "exit_code": returncode,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "output_sha256": digest,
    }
    # Durable evidence intentionally stores no stdout/stderr. Test output can contain credentials,
    # request payloads or customer data; the reviewer gets only a redacted tail in the immediate
    # tool result while long-lived state keeps status + digest.
    _append_evidence(project, task, stage, persisted_record)
    return {
        **persisted_record,
        "stdout_tail": _redact_output(stdout[-MAX_OUTPUT_TAIL_CHARS:], output_secret_values),
        "stderr_tail": _redact_output(stderr[-MAX_OUTPUT_TAIL_CHARS:], output_secret_values),
        "ok": returncode == 0 and not timed_out,
        "sandbox_path": str(root),
        "assurance": "executed-by-ai-layer-in-disposable-working-copy",
    }

def evidence_check_strings(records: list[dict]) -> list[str]:
    result: list[str] = []
    for item in records:
        command = " ".join(str(part) for part in (item.get("command") or []))
        status = "PASS" if int(item.get("exit_code", 1)) == 0 and not item.get("timed_out") else "FAIL"
        result.append(
            "[ai-layer-sandbox] "
            f"{status} {command} (exit={item.get('exit_code')}, duration_ms={item.get('duration_ms')}, "
            f"evidence={item.get('evidence_id')}, output_sha256={item.get('output_sha256')})"
        )
    return result
