from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import yaml

from ai_layer.memory.source import read_text, redact_secrets

COMPOSE_NAME_RE = re.compile(r"^(?:docker-)?compose(?:[._-].*)?\.ya?ml$", re.I)
DB_IMAGE_HINTS = {
    "postgres": "postgresql",
    "postgis": "postgresql",
    "mysql": "mysql",
    "mariadb": "mariadb",
    "mongo": "mongodb",
}
CACHE_IMAGE_HINTS = {"redis": "redis", "memcached": "memcached"}
QUEUE_DEP_HINTS = {
    "celery": "celery",
    "rq": "rq",
    "dramatiq": "dramatiq",
    "horizon": "laravel-horizon",
    "bullmq": "bullmq",
}
INTEGRATION_HINTS = {
    "payments": ("stripe", "yookassa", "paypal", "adyen", "braintree", "payment"),
    "object_storage": ("boto3", "aws-sdk", "s3", "minio", "gcs", "google-cloud-storage"),
    "email": ("sendgrid", "mailgun", "postmark", "smtp", "mailer"),
    "sms": ("twilio", "sms", "vonage"),
    "oauth": ("oauth", "openid", "auth0", "social-auth", "passport"),
    "webhooks": ("webhook", "callback"),
    "observability": ("sentry", "opentelemetry", "prometheus", "datadog"),
}


def _paths(rows: Iterable[object]) -> list[str]:
    return [str(getattr(row, "path", "")) for row in rows if bool(getattr(row, "indexed", True))]


def _dep_text(dependencies: dict[str, list[str]]) -> str:
    return " ".join(str(item) for values in dependencies.values() for item in values).casefold()


def _safe_yaml(root: Path, rel: str) -> dict:
    path = root / rel
    text = read_text(path)
    if not text:
        return {}
    try:
        loaded = yaml.safe_load(text)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _volume_parts(raw: object) -> tuple[str | None, str | None, str | None]:
    if isinstance(raw, str):
        parts = raw.split(":")
        if len(parts) == 1:
            return None, parts[0], None
        return parts[0], parts[1], parts[2] if len(parts) > 2 else None
    if isinstance(raw, dict):
        return (
            str(raw.get("source")) if raw.get("source") is not None else None,
            str(raw.get("target")) if raw.get("target") is not None else None,
            str(raw.get("type")) if raw.get("type") is not None else None,
        )
    return None, None, None


def _mount_role(target: str | None) -> str:
    low = (target or "").casefold()
    if any(
        x in low for x in ("/var/lib/postgresql", "/var/lib/mysql", "/var/lib/mongodb", "/data/db")
    ):
        return "database_data"
    if any(x in low for x in ("/media", "/uploads", "/storage/app/public", "/public/uploads")):
        return "user_media"
    if any(x in low for x in ("/static", "/staticfiles", "/public/build")):
        return "static_or_build_output"
    if any(x in low for x in ("node_modules", "/vendor", "/.venv", "/venv")):
        return "dependency_cache"
    if any(x in low for x in ("/tmp", "/cache", "/var/cache")):
        return "cache_or_temporary"
    if low in {
        "/app",
        "/workspace",
        "/srv/app",
        "/code",
        "/var/www/html",
        "/var/www",
        "/usr/src/app",
    } or low.endswith("/src"):
        return "source_code"
    return "generic_storage"


def docker_topology(root: Path, rows: Iterable[object]) -> dict:
    paths = _paths(rows)
    compose_files = sorted(
        p for p in paths if COMPOSE_NAME_RE.match(Path(p).name) and len(Path(p).parts) <= 4
    )[:12]
    dockerfiles = sorted(p for p in paths if Path(p).name.lower().startswith("dockerfile"))[:20]
    services: dict[str, dict] = {}
    mounts: list[dict] = []
    for rel in compose_files:
        data = _safe_yaml(root, rel)
        raw_services = data.get("services") if isinstance(data.get("services"), dict) else {}
        for name, raw in raw_services.items():
            if not isinstance(raw, dict):
                continue
            service_key = f"{rel}:{name}"
            build = raw.get("build")
            if isinstance(build, dict):
                build_value = {
                    "context": redact_secrets(str(build.get("context") or "")),
                    "dockerfile": redact_secrets(str(build.get("dockerfile") or "")),
                    "target": redact_secrets(str(build.get("target") or "")),
                }
            else:
                build_value = redact_secrets(str(build)) if build is not None else None
            env_keys: list[str] = []
            environment = raw.get("environment")
            if isinstance(environment, dict):
                env_keys = sorted(str(key) for key in environment)[:40]
            elif isinstance(environment, list):
                env_keys = sorted(str(item).split("=", 1)[0] for item in environment)[:40]
            service_mounts = []
            for volume in raw.get("volumes") or []:
                source, target, declared_type = _volume_parts(volume)
                if not target:
                    continue
                inferred_type = declared_type or (
                    "bind"
                    if source
                    and (
                        source.startswith(".") or source.startswith("/") or source.startswith("${")
                    )
                    else "volume"
                )
                item = {
                    "compose": rel,
                    "service": str(name),
                    "source": redact_secrets(source or ""),
                    "target": redact_secrets(target),
                    "type": inferred_type,
                    "role": _mount_role(target),
                }
                mounts.append(item)
                service_mounts.append(item)
            depends = raw.get("depends_on") or []
            if isinstance(depends, dict):
                depends = list(depends)
            services[service_key] = {
                "compose": rel,
                "service": str(name),
                "image": redact_secrets(str(raw.get("image") or "")) or None,
                "build": build_value,
                "command": redact_secrets(str(raw.get("command") or "")) or None,
                "depends_on": sorted(str(x) for x in depends)[:20],
                "ports": [redact_secrets(str(x)) for x in (raw.get("ports") or [])][:20],
                "profiles": [str(x) for x in (raw.get("profiles") or [])][:10],
                "healthcheck": bool(raw.get("healthcheck")),
                "environment_keys": env_keys,
                "env_files": [redact_secrets(str(x)) for x in (raw.get("env_file") or [])][:10]
                if isinstance(raw.get("env_file"), list)
                else ([redact_secrets(str(raw.get("env_file")))] if raw.get("env_file") else []),
                "mounts": service_mounts,
            }
    source_binds = [m for m in mounts if m["type"] == "bind" and m["role"] == "source_code"]
    persistent = [
        m for m in mounts if m["role"] in {"database_data", "user_media", "generic_storage"}
    ]
    signals = []
    if compose_files or dockerfiles:
        signals.append("docker")
    if source_binds:
        signals.append("docker-live-source")
    if any(m["role"] == "database_data" for m in mounts):
        signals.append("persistent-database")
    if any(m["role"] == "user_media" for m in mounts):
        signals.append("persistent-media")
    return {
        "present": bool(compose_files or dockerfiles),
        "compose_files": compose_files,
        "dockerfiles": dockerfiles,
        "services": services,
        "mounts": mounts[:80],
        "source_bind_mounts": source_binds[:20],
        "persistent_mounts": persistent[:30],
        "signals": signals,
    }


def runtime_topology(
    root: Path, rows: Iterable[object], dependencies: dict[str, list[str]], docker: dict
) -> dict:
    paths = _paths(rows)
    names = {Path(p).name for p in paths}
    entries: list[str] = []
    for rel in paths:
        name = Path(rel).name.casefold()
        if name in {
            "manage.py",
            "artisan",
            "app.py",
            "main.py",
            "server.py",
            "wsgi.py",
            "asgi.py",
            "index.js",
            "index.ts",
        }:
            entries.append(rel)
        elif rel.startswith(("routes/", "config/routes", "cmd/")) and len(Path(rel).parts) <= 4:
            entries.append(rel)
    dep_text = _dep_text(dependencies)
    workers: list[str] = []
    schedulers: list[str] = []
    for hint, label in QUEUE_DEP_HINTS.items():
        if hint in dep_text:
            workers.append(label)
    for service in docker.get("services", {}).values():
        command = str(service.get("command") or "").casefold()
        if any(
            x in command
            for x in ("celery worker", "queue:work", "horizon", "rq worker", "dramatiq")
        ):
            workers.append(command[:180])
        if any(x in command for x in ("celery beat", "schedule:work", "schedule:run", "cron")):
            schedulers.append(command[:180])
    if "manage.py" in names and "celery" in dep_text:
        workers.append("celery")
    return {
        "entrypoints": sorted(set(entries))[:40],
        "workers": sorted(set(workers))[:20],
        "schedulers": sorted(set(schedulers))[:20],
        "multiple_runtime_entrypoints": len(set(entries)) > 4,
    }


def data_topology(
    root: Path, rows: Iterable[object], dependencies: dict[str, list[str]], docker: dict
) -> dict:
    paths = _paths(rows)
    dep_text = _dep_text(dependencies)
    stores: set[str] = set()
    caches: set[str] = set()
    for hint, label in DB_IMAGE_HINTS.items():
        if hint in dep_text:
            stores.add(label)
    for hint, label in CACHE_IMAGE_HINTS.items():
        if hint in dep_text:
            caches.add(label)
    for service in docker.get("services", {}).values():
        image = str(service.get("image") or "").casefold()
        name = str(service.get("service") or "").casefold()
        for hint, label in DB_IMAGE_HINTS.items():
            if hint in image or hint in name:
                stores.add(label)
        for hint, label in CACHE_IMAGE_HINTS.items():
            if hint in image or hint in name:
                caches.add(label)
    if any(Path(p).name in {"db.sqlite3", "database.sqlite"} for p in paths):
        stores.add("sqlite")
    media_paths = sorted(
        p
        for p in paths
        if any(part.casefold() in {"media", "uploads"} for part in Path(p).parts[:-1])
    )[:30]
    storage_dirs = sorted(
        {
            Path(p).parts[0]
            for p in paths
            if Path(p).parts and Path(p).parts[0] in {"storage", "media", "uploads"}
        }
    )
    return {
        "databases": sorted(stores),
        "caches": sorted(caches),
        "persistent_mounts": docker.get("persistent_mounts", []),
        "media_evidence_paths": media_paths,
        "storage_roots": storage_dirs,
    }


def testing_topology(rows: Iterable[object], dependencies: dict[str, list[str]]) -> dict:
    paths = _paths(rows)
    test_paths = [
        p
        for p in paths
        if any(
            part.casefold() in {"test", "tests", "spec", "specs", "__tests__"}
            for part in Path(p).parts[:-1]
        )
        or Path(p).name.casefold().startswith(("test_", "spec_"))
        or Path(p).stem.casefold().endswith(("_test", ".test", ".spec"))
    ]
    source_paths = [
        p
        for p in paths
        if Path(p).suffix.casefold()
        in {".py", ".php", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}
    ]
    dep_text = _dep_text(dependencies)
    frameworks = [
        name
        for name in (
            "pytest",
            "unittest",
            "phpunit",
            "pest",
            "jest",
            "vitest",
            "playwright",
            "cypress",
        )
        if name in dep_text
    ]
    ratio = round(len(test_paths) / max(1, len(source_paths)), 3)
    if not source_paths:
        evidence = "unknown_no_code_surface"
    elif not test_paths:
        evidence = "none_detected"
    elif ratio < 0.05:
        evidence = "sparse"
    elif ratio < 0.15:
        evidence = "present"
    else:
        evidence = "substantial"
    return {
        "test_files": len(test_paths),
        "source_files": len(source_paths),
        "observed_test_density": ratio,
        "test_evidence": evidence,
        "frameworks": sorted(set(frameworks)),
        "sample_paths": sorted(test_paths)[:30],
    }


def legacy_fragility(rows: Iterable[object], runtime: dict, testing: dict) -> dict:
    indexed = [row for row in rows if bool(getattr(row, "indexed", True))]
    large_files = [
        str(getattr(row, "path", ""))
        for row in indexed
        if "large_file" in (getattr(row, "risk_flags", None) or [])
    ]
    todo_files = [
        str(getattr(row, "path", ""))
        for row in indexed
        if "contains_todo_or_fixme" in (getattr(row, "risk_flags", None) or [])
    ]
    paths = [str(getattr(row, "path", "")) for row in indexed]
    migration_count = sum(
        1 for p in paths if "migration" in p.casefold() or "/migrations/" in f"/{p.casefold()}/"
    )
    signals: list[dict] = []
    score = 0
    if testing.get("test_evidence") == "none_detected":
        score += 3
        signals.append({"signal": "no_tests_detected", "weight": 3})
    elif testing.get("test_evidence") == "sparse":
        score += 2
        signals.append({"signal": "sparse_test_locality", "weight": 2})
    if large_files:
        weight = 2 if len(large_files) >= 3 else 1
        score += weight
        signals.append(
            {"signal": "large_ownership_files", "weight": weight, "evidence": large_files[:8]}
        )
    if runtime.get("multiple_runtime_entrypoints"):
        score += 1
        signals.append({"signal": "multiple_runtime_entrypoints", "weight": 1})
    if migration_count >= 40:
        score += 1
        signals.append({"signal": "large_migration_history", "weight": 1, "count": migration_count})
    if len(todo_files) >= 8:
        score += 1
        signals.append({"signal": "many_todo_fixme_files", "weight": 1, "count": len(todo_files)})
    level = "high" if score >= 5 else "medium" if score >= 2 else "low"
    return {
        "level": level,
        "score": score,
        "signals": signals,
        "note": "Evidence-based change-fragility profile, not an assertion that the project is old or poorly designed.",
    }


def integration_topology(rows: Iterable[object], dependencies: dict[str, list[str]]) -> dict:
    paths = _paths(rows)
    dep_text = _dep_text(dependencies)
    result: dict[str, list[str]] = {}
    for domain, hints in INTEGRATION_HINTS.items():
        evidence = [hint for hint in hints if hint in dep_text]
        evidence.extend(p for p in paths[:5000] if any(hint in p.casefold() for hint in hints))
        if evidence:
            result[domain] = sorted(set(evidence))[:20]
    return result
