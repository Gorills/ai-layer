from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ai_layer.memory.intelligence_runtime import (
    data_topology,
    docker_topology,
    integration_topology,
    legacy_fragility,
    runtime_topology,
    testing_topology,
)
from ai_layer.memory.intelligence_web import (
    design_profile,
    documentation_profile,
    frontend_topology,
    seo_profile,
)

DOMAIN_TASK_TERMS = {
    "docker": ("docker", "compose", "container", "image", "volume", "mount", "deploy", "deployment"),
    "runtime": ("startup", "entrypoint", "worker", "queue", "scheduler", "cron", "process", "run"),
    "data": ("database", "postgres", "mysql", "redis", "storage", "media", "upload", "persistence", "migration"),
    "frontend": ("frontend", "ui", "component", "react", "vue", "svelte", "javascript", "typescript", "html", "css", "browser"),
    "design": ("design", "layout", "style", "spacing", "typography", "responsive", "pixel", "visual", "ui", "ux"),
    "seo": ("seo", "search", "google", "yandex", "index", "canonical", "sitemap", "robots", "structured data", "schema"),
    "testing": ("test", "pytest", "phpunit", "pest", "playwright", "cypress", "regression", "coverage"),
    "documentation": ("readme", "documentation", "docs", "deploy", "configuration", "env", "api contract", "runbook"),
    "integrations": ("webhook", "payment", "email", "sms", "oauth", "s3", "integration", "provider"),
    "legacy": ("legacy", "refactor", "fragile", "brittle", "existing behavior", "compatibility"),
}


def _dep_text(dependencies: dict[str, list[str]]) -> str:
    return " ".join(str(item) for values in dependencies.values() for item in values).casefold()


def _stack_profile(root: Path, rows: Iterable[object], languages: dict[str, int], dependencies: dict[str, list[str]]) -> dict:
    paths = {str(getattr(row, "path", "")) for row in rows if bool(getattr(row, "indexed", True))}
    dep_text = _dep_text(dependencies)
    frameworks: list[str] = []
    signals = {
        "django": "django" in dep_text or "manage.py" in paths,
        "fastapi": "fastapi" in dep_text,
        "laravel": "laravel/framework" in dep_text or "artisan" in paths,
        "react": "react@" in dep_text or " react" in dep_text,
        "vue": "vue@" in dep_text or " vue" in dep_text,
        "svelte": "svelte@" in dep_text or " svelte" in dep_text,
        "node": "node" in dependencies or "package.json" in paths,
        "php": "php" in languages or "composer.json" in paths,
        "python": "python" in languages or "python" in dependencies,
    }
    frameworks.extend(name for name, present in signals.items() if present and name not in {"php", "python", "node"})
    manifests = sorted(
        p for p in paths
        if Path(p).name in {
            "pyproject.toml", "requirements.txt", "package.json", "package-lock.json", "pnpm-lock.yaml",
            "yarn.lock", "composer.json", "composer.lock", "go.mod", "Cargo.toml", "project.godot",
        }
    )[:30]
    details: dict[str, dict] = {}
    if signals["django"]:
        settings = sorted(p for p in paths if Path(p).name == "settings.py" or "/settings/" in f"/{p}")[:20]
        urls = sorted(p for p in paths if Path(p).name == "urls.py")[:30]
        apps = sorted({
            str(Path(p).parent) for p in paths
            if Path(p).name == "apps.py" or (Path(p).name == "models.py" and len(Path(p).parts) <= 5)
        })[:40]
        details["django"] = {
            "manage_py": "manage.py" in paths,
            "settings_evidence": settings,
            "urlconf_evidence": urls,
            "app_roots": apps,
            "migration_files": sum(1 for p in paths if "/migrations/" in f"/{p}" and p.endswith(".py")),
            "media_or_static_evidence": sorted(p for p in paths if any(part.casefold() in {"media", "static", "staticfiles"} for part in Path(p).parts))[:20],
        }
    if signals["laravel"]:
        details["laravel"] = {
            "artisan": "artisan" in paths,
            "route_files": sorted(p for p in paths if p.startswith("routes/") and p.endswith(".php"))[:30],
            "config_files": sorted(p for p in paths if p.startswith("config/") and p.endswith(".php"))[:30],
            "application_roots": sorted({
                "/".join(Path(p).parts[:2]) for p in paths
                if len(Path(p).parts) >= 2 and Path(p).parts[0] == "app"
            })[:40],
            "migration_files": sum(1 for p in paths if p.startswith("database/migrations/") and p.endswith(".php")),
            "storage_evidence": sorted(p for p in paths if p.startswith("storage/"))[:20],
        }
    return {
        "languages": sorted(languages, key=languages.get, reverse=True),
        "frameworks": sorted(set(frameworks)),
        "dependency_ecosystems": sorted(dependencies),
        "manifests": manifests,
        "framework_details": details,
    }


def build_project_intelligence(
    root: Path,
    rows: Iterable[object],
    languages: dict[str, int],
    dependencies: dict[str, list[str]],
) -> dict:
    rows = list(rows)
    stack = _stack_profile(root, rows, languages, dependencies)
    docker = docker_topology(root, rows)
    runtime = runtime_topology(root, rows, dependencies, docker)
    data = data_topology(root, rows, dependencies, docker)
    testing = testing_topology(rows, dependencies)
    legacy = legacy_fragility(rows, runtime, testing)
    frontend = frontend_topology(root, rows, dependencies)
    design = design_profile(root, rows, dependencies, frontend)
    seo = seo_profile(root, rows, dependencies, frontend)
    documentation = documentation_profile(root, rows)
    integrations = integration_topology(rows, dependencies)

    signals: set[str] = set()
    signals.update(stack.get("frameworks") or [])
    signals.update(stack.get("languages") or [])
    if docker.get("present"):
        signals.add("docker")
    signals.update(docker.get("signals") or [])
    if frontend.get("present"):
        signals.add("frontend")
    if design.get("design_system_signal") == "explicit_tokens":
        signals.add("design-system")
    if seo.get("public_web_surface"):
        signals.update({"public-web", "seo-surface"})
    if documentation.get("has_project_docs"):
        signals.add("project-docs")
    if testing.get("test_files", 0):
        signals.add("tests")
    if legacy.get("level") in {"medium", "high"}:
        signals.add("legacy-fragility")
    if integrations:
        signals.add("external-integrations")

    return {
        "schema": 1,
        "stack": stack,
        "runtime": runtime,
        "data": data,
        "docker": docker,
        "frontend": frontend,
        "design": design,
        "seo": seo,
        "testing": testing,
        "legacy": legacy,
        "documentation": documentation,
        "integrations": integrations,
        "signals": sorted(signals),
        "assurance": (
            "Deterministic scanner evidence. It describes observed files/manifests/configuration and risk signals; "
            "it does not replace current-source inspection or prove runtime behavior that was not executed."
        ),
    }


def compact_architecture_summary(root: Path, intelligence: dict) -> str:
    stack = intelligence.get("stack") or {}
    runtime = intelligence.get("runtime") or {}
    data = intelligence.get("data") or {}
    docker = intelligence.get("docker") or {}
    testing = intelligence.get("testing") or {}
    legacy = intelligence.get("legacy") or {}
    frontend = intelligence.get("frontend") or {}
    docs = intelligence.get("documentation") or {}
    return (
        f"Project `{root.name}`. Languages: {stack.get('languages') or []}. "
        f"Frameworks: {stack.get('frameworks') or []}. "
        f"Runtime entrypoints: {(runtime.get('entrypoints') or [])[:10]}. "
        f"Data stores: {data.get('databases') or []}; caches: {data.get('caches') or []}. "
        f"Docker: {'present' if docker.get('present') else 'not detected'}; "
        f"frontend: {frontend.get('frameworks') or []}. "
        f"Tests: {testing.get('test_evidence', 'unknown')} ({testing.get('test_files', 0)} files). "
        f"Change-fragility: {legacy.get('level', 'unknown')}. "
        f"Documentation domains: {sorted((docs.get('domains') or {}).keys())}. "
        "This summary is scanner-derived evidence, not an invented architecture description."
    )


def _domain_has_retrievable_evidence(domain: str, value: object) -> bool:
    if not isinstance(value, dict) or not value:
        return bool(value)
    if domain == "stack":
        return bool(value.get("languages") or value.get("frameworks") or value.get("manifests"))
    if domain == "runtime":
        return bool(value.get("entrypoints") or value.get("workers") or value.get("schedulers"))
    if domain == "data":
        return bool(value.get("databases") or value.get("caches") or value.get("persistent_mounts") or value.get("media_evidence_paths") or value.get("storage_roots"))
    if domain == "docker":
        return bool(value.get("present"))
    if domain == "frontend":
        return bool(value.get("present"))
    if domain == "design":
        return bool(value.get("evidence_files") or value.get("css_custom_properties") or value.get("component_libraries"))
    if domain == "seo":
        return bool(value.get("public_web_surface") or value.get("robots_files") or value.get("sitemap_files") or value.get("marker_evidence"))
    if domain == "testing":
        return bool(value.get("source_files") or value.get("test_files") or value.get("frameworks"))
    if domain == "legacy":
        return bool(value.get("signals"))
    if domain == "documentation":
        return bool(value.get("has_project_docs"))
    return bool(value)
