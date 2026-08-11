from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

import yaml


@dataclass(frozen=True)
class DoctorDependencies:
    version: str
    integration_template_version: int
    get_settings: Callable[[], Any]
    docker_compose_available: Callable[[], tuple[bool, str | None]]
    database_status: Callable[[], dict]
    global_integration_status: Callable[[], dict]
    global_bootstrap_status: Callable[[], dict]
    list_registered_projects: Callable[[], list[dict]]
    list_mcp_processes: Callable[[], list[dict]]
    read_install_state: Callable[[], dict]
    service_status: Callable[[], dict]
    get_registered_project: Callable[[Path], dict | None]
    normalize_root: Callable[[str], Path]
    project_config_path: Callable[[Path], Path]
    project_mode: Callable[[Path], str]
    project_provenance: Callable[[Path], dict]
    project_meta_dir: Callable[[Path], Path]
    integration_status: Callable[[Path], dict]
    repository_footprint: Callable[[Path], dict]
    privacy_check: Callable[[Path], dict]
    git_privacy_guard_status: Callable[[Path], dict]
    overlapping_registered_projects: Callable[[str | Path], list[dict]]


def _machine_state(deps: DoctorDependencies) -> dict:
    settings = deps.get_settings()
    compose_ok, docker = deps.docker_compose_available()
    stable_cli = settings.stable_bin_dir / "ai-layer"
    stable_mcp = settings.stable_mcp_executable
    return {
        "version": deps.version,
        "install_state": deps.read_install_state(),
        "stable_cli": {"path": str(stable_cli), "exists": stable_cli.exists()},
        "stable_mcp": {"path": str(stable_mcp), "exists": stable_mcp.exists()},
        "config": {"path": str(settings.config_file), "exists": settings.config_file.exists()},
        "runtime_assets": {
            "compose": (settings.machine_runtime_dir / "docker-compose.yml").exists(),
            "alembic": (settings.machine_runtime_dir / "alembic").exists(),
        },
        "docker_compose": {"available": compose_ok, "executable": docker},
        "database": deps.database_status(),
        "global_integrations": deps.global_integration_status(),
        "global_bootstrap": deps.global_bootstrap_status(),
        "registry": {"path": str(settings.projects_registry_file), "count": len(deps.list_registered_projects())},
        "mcp_processes": deps.list_mcp_processes(),
        "service": deps.service_status(),
    }


def _selected_roots(deps: DoctorDependencies, *, path: str | None, all_projects: bool, machine_only: bool) -> list[Path]:
    if machine_only:
        return []
    roots: list[Path] = []
    if path:
        roots.append(deps.normalize_root(path))
    elif deps.get_registered_project(Path.cwd()) is not None and deps.project_config_path(Path.cwd()).exists():
        roots.append(Path.cwd().resolve())
    if all_projects:
        roots.extend(
            Path(str(item["root"])).resolve()
            for item in deps.list_registered_projects()
            if item.get("root")
        )
    seen: set[str] = set()
    return [root for root in roots if not (str(root) in seen or seen.add(str(root)))]


def _project_state(deps: DoctorDependencies, root: Path) -> dict:
    item: dict = {"root": str(root), "exists": root.exists()}
    if not root.exists():
        item.update({"initialized": False, "ready": False})
        return item
    try:
        config_file = deps.project_config_path(root)
    except RuntimeError as exc:
        item.update({"initialized": False, "ready": False, "unsafe_path": str(exc)})
        return item
    if not config_file.exists():
        item.update({"initialized": False, "ready": False})
        return item

    config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    item.update({
        "initialized": True,
        "configured_template_version": config.get("integration_template_version"),
        "current_template_version": deps.integration_template_version,
        "drift": config.get("integration_template_version") != deps.integration_template_version,
        "mode": deps.project_mode(root),
        "provenance": deps.project_provenance(root),
        "state_dir": str(deps.project_meta_dir(root)),
        "integrations": deps.integration_status(root),
    })
    if item["integrations"].get("unsafe_path"):
        item["unsafe_path"] = item["integrations"]["unsafe_path"]
    if item["mode"] != "strict-private":
        item["ready"] = not item["drift"] and item["integrations"]["ready"]
        return item

    item["footprint"] = deps.repository_footprint(root)
    item["privacy_check"] = deps.privacy_check(root)
    item["git_guard"] = deps.git_privacy_guard_status(root)
    privacy_ready = (
        not item["footprint"]["repository_ai_artifacts"]
        and not item["footprint"]["tracked_ai_or_provenance"]
        and not item["footprint"].get("tracked_unscannable", [])
        and item["privacy_check"].get("ok", False)
        and item["git_guard"].get("ready", False)
    )
    item["strict_private_ready"] = privacy_ready
    item["ready"] = not item["drift"] and item["integrations"]["ready"] and privacy_ready
    return item


def _machine_issues(deps: DoctorDependencies, machine: dict, *, runtime_ready: bool, db_ready: bool) -> list[dict]:
    issues: list[dict] = []
    if not runtime_ready:
        issues.append({"severity": "error", "problem": "stable runtime launcher is missing", "action": "re-run ./install.sh from the release archive"})
    if not machine["docker_compose"]["available"]:
        issues.append({"severity": "error", "problem": "Docker Compose is unavailable", "action": "install Docker + compose plugin, then run ai-layer upgrade"})
    if not db_ready:
        issues.append({"severity": "error", "problem": "PostgreSQL/pgvector is not ready", "action": "ai-layer upgrade"})
    for provider, state in machine["global_integrations"].items():
        if not state["ready"]:
            issues.append({"severity": "error", "problem": f"global {provider} MCP integration is missing", "action": "ai-layer upgrade"})
    for provider, state in machine["global_bootstrap"].items():
        if not state.get("ready"):
            issues.append({"severity": "warning", "problem": f"global {provider} bootstrap instruction is missing", "action": "ai-layer upgrade"})
    cursor_bootstrap = machine["global_bootstrap"].get("cursor", {})
    if cursor_bootstrap.get("ready") and cursor_bootstrap.get("runtime_acceptance_required"):
        issues.append({
            "severity": "warning",
            "problem": "Cursor global bootstrap files are installed; one real-agent black-box acceptance is still a machine-level validation step, not a project error",
            "action": "run docs/BLACK-BOX_PROJECT_INTELLIGENCE_v0.7.0_RU.md once on the supported release host",
        })
    for process in machine["mcp_processes"]:
        if not process.get("version_match", True):
            issues.append({
                "severity": "warning",
                "problem": f"stale MCP process {process.get('pid')} is version {process.get('version')} while installed runtime is {deps.version}",
                "action": "reconnect/restart the IDE MCP host when convenient",
            })
    issues.extend(_service_issues(machine.get("service") or {}))
    return issues


def _service_issues(service_state: dict) -> list[dict]:
    issues: list[dict] = []
    autostart = service_state.get("autostart") or {}
    if autostart.get("supported") and not autostart.get("enabled"):
        issues.append({"severity": "warning", "problem": "always-on AI Layer service autostart is not enabled", "action": "ai-layer service install"})
    elif autostart.get("supported") and not service_state.get("running"):
        issues.append({"severity": "warning", "problem": "always-on AI Layer service is enabled but not reachable", "action": "ai-layer service restart"})
    core = service_state.get("core_runtime") or {}
    if service_state.get("running") and core.get("status") == "degraded":
        issues.append({
            "severity": "error",
            "problem": "persistent AI Layer core runtime is degraded",
            "details": {"warm_error": core.get("warm_error")},
            "action": "ai-layer health; restore database/runtime dependencies, then run ai-layer service restart",
        })
    elif service_state.get("running") and core.get("status") in {"starting", "warming"}:
        issues.append({"severity": "warning", "problem": f"persistent AI Layer core runtime is {core.get('status')}", "action": "ai-layer health"})
    return issues


def _overlap_issues(deps: DoctorDependencies, projects: list[dict]) -> list[dict]:
    issues: list[dict] = []
    pairs: set[tuple[str, str]] = set()
    selected = {str(item.get("root")) for item in projects if item.get("root")}
    for item in projects:
        root = item.get("root")
        if not root:
            continue
        for conflict in deps.overlapping_registered_projects(root):
            other = str(conflict.get("root") or "")
            pair = tuple(sorted((str(root), other)))
            if other not in selected or pair in pairs:
                continue
            pairs.add(pair)
            first, second = Path(pair[0]).resolve(), Path(pair[1]).resolve()
            try:
                second.relative_to(first)
                parent, child = str(first), str(second)
            except ValueError:
                parent, child = str(second), str(first)
            issues.append({
                "severity": "error",
                "problem": f"overlapping project registrations: {parent} contains {child}",
                "action": "run ai-layer repair; the current repair keeps the parent registration and safely detaches nested registrations",
            })
    return issues


def _strict_private_issue(item: dict) -> dict:
    footprint, changed, guard = item.get("footprint", {}), item.get("privacy_check", {}), item.get("git_guard", {})
    details = {
        "repository_ai_artifacts": footprint.get("repository_ai_artifacts", []),
        "tracked_ai_or_provenance": footprint.get("tracked_ai_or_provenance", []),
        "tracked_unscannable": footprint.get("tracked_unscannable", []),
        "changed_privacy_violations": changed.get("violations", []),
        "git_guard": guard,
    }
    manual: list[str] = []
    if details["tracked_ai_or_provenance"]:
        manual.append("review/remove AI provenance from the listed tracked files")
    if details["tracked_unscannable"]:
        manual.append("review the listed unscannable tracked files")
    if details["changed_privacy_violations"]:
        manual.append("review the listed changed/staged privacy violations")
    if not guard.get("ready", False):
        manual.append("resolve the Git core.hooksPath/privacy-guard conflict")
    if details["repository_ai_artifacts"]:
        manual.append("run ai-layer repair --path on this root; remaining artifacts are shown above")
    return {
        "severity": "error",
        "problem": f"strict-private project still needs manual attention: {item['root']}",
        "details": details,
        "action": "; ".join(manual) or f"ai-layer repair --path {item['root']}",
    }


def _project_issues(projects: list[dict]) -> list[dict]:
    issues: list[dict] = []
    for item in projects:
        if not item.get("exists"):
            issues.append({"severity": "warning", "problem": f"registered project path no longer exists: {item['root']}", "action": "ai-layer projects prune"})
        elif item.get("unsafe_path"):
            issues.append({
                "severity": "error",
                "problem": f"unsafe project metadata path: {item['root']}",
                "action": "replace project-local AI Layer symlinks with real files/directories, then run ai-layer sync",
            })
        elif item.get("mode") == "strict-private" and not item.get("strict_private_ready", False):
            issues.append(_strict_private_issue(item))
        elif item.get("drift") or not item.get("ready"):
            issues.append({"severity": "error", "problem": f"project integration drift: {item['root']}", "action": f"ai-layer repair --path {item['root']}"})
    return issues


def doctor_report(deps: DoctorDependencies, *, path: str | None = None, all_projects: bool = False, machine_only: bool = False) -> dict:
    if machine_only and (path or all_projects):
        raise ValueError("--machine-only cannot be combined with --path or --all-projects")
    machine = _machine_state(deps)
    projects = [_project_state(deps, root) for root in _selected_roots(deps, path=path, all_projects=all_projects, machine_only=machine_only)]
    global_ready = all(item["ready"] for item in machine["global_integrations"].values())
    runtime_ready = machine["stable_cli"]["exists"] and machine["stable_mcp"]["exists"]
    db_ready = bool(machine["database"].get("connected") and machine["database"].get("pgvector"))
    existing = [item for item in projects if item.get("exists")]
    project_ready = all(item.get("ready", False) for item in existing) if existing else True
    issues = [
        *_machine_issues(deps, machine, runtime_ready=runtime_ready, db_ready=db_ready),
        *_overlap_issues(deps, projects),
        *_project_issues(projects),
    ]
    ready = runtime_ready and global_ready and db_ready and project_ready
    ready = ready and not any(issue.get("severity") == "error" for issue in issues)
    return {"ok": ready, "machine": machine, "projects": projects, "issues": issues}
