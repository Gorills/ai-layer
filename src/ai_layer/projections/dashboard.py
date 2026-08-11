from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ai_layer.application.tasks import read_state as read_task_state
from ai_layer.core.background_service import service_runtime_payload
from ai_layer.core.mcp_runtime import runtime_state as core_runtime_state
from ai_layer.core.registry import list_registered_projects
from ai_layer.core.service import get_project
from ai_layer.db.models import VerificationRun
from ai_layer.db.session import session_scope
from ai_layer.observability.domain_events import read_structured_events
from ai_layer.observability.events import aggregate_events, parse_ts
from ai_layer.observability.snapshot import observability_snapshot
from ai_layer.skills.native import native_catalog_files


def _project_key(entry: dict) -> str:
    project_id = str(entry.get("project_id") or "").strip()
    if project_id:
        return project_id
    root = str(entry.get("root") or "")
    return "root-" + hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def _entry_for_key(key: str) -> dict | None:
    for entry in list_registered_projects(existing_only=True):
        if _project_key(entry) == key:
            return dict(entry)
    return None


def _processes_for_root(processes: list[dict], root: Path, known_roots: list[Path]) -> list[dict]:
    result: list[dict] = []
    resolved_root = root.resolve()
    ordered_roots = sorted(
        (item.resolve() for item in known_roots),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for process in processes:
        raw = str(process.get("last_project_root") or "").strip()
        if not raw:
            continue
        try:
            candidate = Path(raw).expanduser().resolve()
        except OSError:
            continue
        owner = None
        for known in ordered_roots:
            try:
                candidate.relative_to(known)
                owner = known
                break
            except ValueError:
                continue
        if owner == resolved_root:
            result.append(dict(process))
    return result


def _runtime_state(project: dict, agents: list[dict], task_state: dict | None = None) -> str:
    """Compatibility activity state. Protocol failures never make the project itself an error."""
    current_task = (task_state or {}).get("current") or {}
    if current_task.get("status") == "blocked":
        return "blocked"
    if current_task.get("status") == "active":
        return "active"
    if project.get("active_operations") or any(
        item.get("activity_state") in {"ACTIVE", "WORKING"} for item in agents
    ):
        return "active"
    return "idle"


def _project_state(project: dict, agents: list[dict], task_state: dict | None = None) -> str:
    current_task = (task_state or {}).get("current") or {}
    if current_task.get("human_attention_required"):
        return "attention"
    if (
        current_task.get("status") == "active"
        or project.get("active_operations")
        or any(item.get("activity_state") in {"ACTIVE", "WORKING"} for item in agents)
    ):
        return "working"
    return "healthy"


def _protocol_state(project: dict) -> dict:
    stats = project.get("last_5m") or {}
    failed_count = int(stats.get("failed") or 0)
    recent = []
    cutoff = datetime.now(UTC) - timedelta(minutes=5)
    for event in project.get("recent_events") or []:
        if event.get("status") not in {"completed", "failed"}:
            continue
        event_at = parse_ts(event.get("ts"))
        if event_at is None or event_at < cutoff:
            continue
        recent.append(event)
    recent.sort(key=lambda item: str(item.get("ts") or ""))
    failures = [item for item in recent if item.get("status") == "failed"]
    last_failure = failures[-1] if failures else None
    recovered = False
    if last_failure is not None:
        failed_at = parse_ts(last_failure.get("ts"))
        if failed_at is not None:
            recovered = any(
                item.get("status") == "completed"
                and item.get("operation") == last_failure.get("operation")
                and (completed_at := parse_ts(item.get("ts"))) is not None
                and completed_at > failed_at
                for item in recent
            )
    elif failed_count:
        # The 5-minute aggregate can contain more events than the compact recent-events tail.
        # Do not invent recovery evidence when the failed event itself is no longer visible.
        recovered = False

    normalizations = sum(
        int((item.get("metrics") or {}).get("normalization_count") or 0)
        for item in recent
        if item.get("status") == "completed"
    )
    return {
        "status": "warning" if failed_count else "healthy",
        "failures_5m": failed_count,
        "recovered": recovered,
        "last_failure_at": last_failure.get("ts") if last_failure else None,
        "last_failure_operation": last_failure.get("operation") if last_failure else None,
        "last_error_type": last_failure.get("error_type") if last_failure else None,
        "normalizations_5m": normalizations,
    }


def _terminal_events(events: list[dict]) -> list[dict]:
    return [item for item in events if item.get("status") in {"completed", "failed"}]


def _event_summary(event: dict, project: dict) -> dict:
    return {
        "ts": event.get("ts"),
        "project_key": project.get("key"),
        "project_name": project.get("name"),
        "client": event.get("client") or "unknown",
        "category": event.get("category") or "unknown",
        "operation": event.get("operation") or "unknown",
        "status": event.get("status") or "unknown",
        "duration_ms": event.get("duration_ms"),
        "error_type": event.get("error_type"),
        "metrics": event.get("metrics") or {},
    }


def _safe_database_status(value: dict) -> dict:
    return {
        "connected": bool(value.get("connected")),
        "pgvector": value.get("pgvector"),
        "error": "database unavailable" if not value.get("connected") else None,
    }


def _latest_memory_context_skill_state(events: list[dict]) -> dict:
    completed = [
        item
        for item in events
        if item.get("operation") == "memory_context" and item.get("status") == "completed"
    ]
    if not completed:
        return {"seen": False, "at": None, "routing_owner": "host-native"}
    event = max(completed, key=lambda item: str(item.get("ts") or ""))
    metrics = event.get("metrics") or {}
    return {
        "seen": True,
        "at": event.get("ts"),
        "routing_owner": str(metrics.get("skill_routing_owner") or "host-native"),
        "automatic_skill_injection": bool(metrics.get("automatic_skill_injection", False)),
        "automatic_skill_chars": int(metrics.get("automatic_skill_chars") or 0),
    }


def _task_skill_state(root: Path, task: dict | None, events: list[dict]) -> dict:
    last_context = _latest_memory_context_skill_state(events)
    fetches = []
    for event in events:
        if event.get("operation") != "skill_get" or event.get("status") != "completed":
            continue
        metrics = event.get("metrics") or {}
        slug = str(metrics.get("skill_slug") or "")
        if not slug:
            continue
        section = str(metrics.get("section") or "full")
        fetches.append(
            {
                "slug": slug,
                "section": section,
                "full": section.casefold() == "full",
                "at": event.get("ts"),
            }
        )
    catalogs = native_catalog_files(root)
    return {
        "task": task.get("key") if task and task.get("status") in {"active", "blocked"} else None,
        "routing_owner": "host-native",
        "ai_layer_planner_active": False,
        "configured_catalog": {host: len(paths) for host, paths in catalogs.items()},
        "observed_fetches": fetches[-20:],
        "last_context": last_context,
        "source": "native-catalog-plus-observed-skill-get",
        "note": (
            "AI Layer configures thin native descriptors and observes explicit skill_get delivery. "
            "Host selection/activation itself is not observable, so automatic and manual activation are not distinguished."
        ),
    }


def _structured_event_summary(event: dict) -> dict:
    """Expose event identity/state to the read side without arbitrary domain payload content."""
    return {
        "event_type": event.get("event_type"),
        "project_id": event.get("project_id"),
        "aggregate_type": event.get("aggregate_type"),
        "aggregate_id": event.get("aggregate_id"),
        "created_at": event.get("created_at"),
        "payload_fields": sorted(str(key) for key in (event.get("payload") or {}).keys()),
    }


def _durable_read_models(root: Path, task_state: dict, agents: list[dict]) -> dict:
    """Project read-side projection for Dashboard; no mutation/business transition lives here."""
    task = task_state.get("current") or task_state.get("latest") or {}
    stages = list(task.get("stages") or [])
    findings = list(task.get("findings") or task.get("active_findings") or [])
    worker_rows = [
        {
            "stage_id": item.get("id"),
            "stage": item.get("kind"),
            "status": item.get("status"),
            "worker_id": item.get("worker_id"),
            "requested_model": (
                (item.get("model_identity") or {}).get("requested") or item.get("agent_model")
            ),
            "actual_model": (item.get("model_identity") or {}).get("actual"),
            "model_assurance": (item.get("model_identity") or {}).get("assurance"),
            "telemetry": item.get("telemetry") or {},
        }
        for item in stages
        if item.get("worker_id")
    ]
    verifications: list[dict] = []
    events: list[dict] = []
    try:
        with session_scope() as db:
            project = get_project(db, root)
            if project is not None:
                rows = db.scalars(
                    select(VerificationRun)
                    .where(VerificationRun.project_id == project.id)
                    .order_by(VerificationRun.created_at.desc())
                    .limit(50)
                ).all()
                verifications = [
                    {
                        "id": str(row.id),
                        "task_id": str(row.task_id) if row.task_id else None,
                        "stage_id": str(row.stage_id) if row.stage_id else None,
                        "assurance": row.assurance,
                        "command": list(row.command or []),
                        "started_at": row.started_at.isoformat(),
                        "completed_at": row.completed_at.isoformat(),
                        "exit_code": row.exit_code,
                        "timed_out": bool(row.timed_out),
                        "output_summary": row.output_summary,
                        "evidence_ref": row.evidence_ref,
                    }
                    for row in rows
                ]
                events = read_structured_events(db, project=project, limit=80)
    except Exception as exc:
        events = [
            {
                "event_type": "ProjectionReadError",
                "project_id": None,
                "aggregate_type": "projection",
                "aggregate_id": "dashboard",
                "payload": {"message": f"{type(exc).__name__}: {exc}"[:500]},
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]
    events = [_structured_event_summary(event) for event in events]
    blockers = []
    if task.get("status") == "blocked":
        blockers.append(
            {
                "task": task.get("key"),
                "reason": task.get("blocked_reason"),
                "human_attention_required": bool(task.get("human_attention_required")),
            }
        )
    errors = [
        event
        for event in events
        if event.get("event_type") in {"AgentFailed", "StageInvalidated", "TaskBlocked"}
    ]
    return {
        "machine_health": {
            "service": service_runtime_payload(),
            "core_runtime": core_runtime_state(),
        },
        "active_task": task if task.get("status") in {"active", "blocked"} else None,
        "stage_timeline": stages,
        "workers": worker_rows,
        "host_agents": agents,
        "model_assurance": [
            {
                "stage_id": item.get("stage_id"),
                "requested": item.get("requested_model"),
                "actual": item.get("actual_model"),
                "assurance": item.get("model_assurance"),
            }
            for item in worker_rows
        ],
        "verification": verifications,
        "findings": findings,
        "blockers": blockers,
        "recent_events": events,
        "recent_errors": errors,
    }


def overview_payload() -> dict:
    snapshot = observability_snapshot(all_projects=True, include_handoff_text=False)
    processes = snapshot.get("mcp_processes") or []
    projects: list[dict] = []
    timeline: list[dict] = []
    total_completed = 0
    total_failed = 0
    active_tasks = 0
    blocked_tasks = 0
    attention_tasks = 0
    protocol_warnings = 0
    recovered_protocol_warnings = 0
    project_p95_values: list[float] = []

    snapshot_projects = snapshot.get("projects") or []
    known_roots = [Path(str(item["root"])) for item in snapshot_projects]
    for project in snapshot_projects:
        root = Path(str(project["root"]))
        agents = _processes_for_root(processes, root, known_roots)
        stats = project.get("last_5m") or {}
        completed = int(stats.get("completed") or 0)
        failed = int(stats.get("failed") or 0)
        total_completed += completed
        total_failed += failed
        task_state = read_task_state(root)
        current_task = task_state.get("current") or {}
        if current_task.get("status") == "active":
            active_tasks += 1
        elif current_task.get("status") == "blocked":
            blocked_tasks += 1
            if current_task.get("human_attention_required"):
                attention_tasks += 1
        protocol = _protocol_state(project)
        if protocol["status"] == "warning":
            protocol_warnings += 1
            if protocol["recovered"]:
                recovered_protocol_warnings += 1
        latency = project.get("mcp_latency") or {}
        if isinstance(latency.get("p95_ms"), (int, float)):
            project_p95_values.append(float(latency["p95_ms"]))
        card = {
            "key": _project_key({"project_id": project.get("project_id"), "root": str(root)}),
            "name": project.get("name") or root.name,
            "root": str(root),
            "mode": project.get("mode") or "standard",
            "provenance": project.get("provenance") or "allow",
            "runtime_state": _runtime_state(project, agents, task_state),
            "project_state": _project_state(project, agents, task_state),
            "task_state": current_task.get("status") or "none",
            "protocol_state": protocol,
            "last_scan": project.get("last_scan"),
            "scan_reason": project.get("scan_reason"),
            "scan_files": project.get("scan_files"),
            "agents": agents,
            "task": current_task or task_state.get("latest"),
            "task_active": bool(current_task),
            "next_action": task_state.get("next_action"),
            "active_operations": project.get("active_operations") or [],
            "last_5m": stats,
            "mcp_latency": latency,
            "memory_refresh": project.get("memory_refresh") or {"status": "idle"},
        }
        projects.append(card)
        for event in _terminal_events(project.get("recent_events") or [])[-8:]:
            timeline.append(_event_summary(event, card))

    timeline.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    active_agents = sum(
        1 for item in processes if item.get("activity_state") in {"ACTIVE", "WORKING"}
    )
    db = _safe_database_status(snapshot.get("database") or {})
    return {
        "version": snapshot.get("version"),
        "generated_at": snapshot.get("generated_at"),
        "privacy": snapshot.get("privacy"),
        "service": service_runtime_payload(),
        "core_runtime": core_runtime_state(),
        "database": db,
        "summary": {
            "projects": len(projects),
            "active_agents": active_agents,
            "mcp_processes": len(processes),
            "active_tasks": active_tasks,
            "blocked_tasks": blocked_tasks,
            "attention_tasks": attention_tasks,
            "operations_5m": total_completed,
            "failures_5m": total_failed,
            "protocol_warnings": protocol_warnings,
            "mcp_worst_project_p95_ms": round(max(project_p95_values), 1)
            if project_p95_values
            else None,
            "recovered_protocol_warnings": recovered_protocol_warnings,
        },
        "projects": sorted(
            projects,
            key=lambda item: (
                0
                if item.get("task_state") == "blocked"
                else 1
                if item.get("task_state") == "active"
                else 2,
                0 if (item.get("protocol_state") or {}).get("status") == "warning" else 1,
                str(item["name"]).lower(),
            ),
        ),
        "recent_activity": timeline[:24],
    }


def project_payload(key: str) -> dict | None:
    entry = _entry_for_key(key)
    if entry is None:
        return None
    root = Path(str(entry["root"]))
    snapshot = observability_snapshot(root, include_handoff_text=False)
    if not snapshot.get("projects"):
        return None
    project = snapshot["projects"][0]
    agents = _processes_for_root(snapshot.get("mcp_processes") or [], root, [root])
    metrics_24h = aggregate_events(root, since_seconds=24 * 3600, recent_limit=80)
    terminal = metrics_24h["recent_terminal"]
    task_state = read_task_state(root)
    skill_state = _task_skill_state(root, task_state.get("current"), terminal)
    return {
        "version": snapshot.get("version"),
        "generated_at": snapshot.get("generated_at"),
        "privacy": snapshot.get("privacy"),
        "service": service_runtime_payload(),
        "database": _safe_database_status(snapshot.get("database") or {}),
        "project": {
            "key": key,
            "name": project.get("name") or root.name,
            "root": str(root),
            "mode": project.get("mode") or "standard",
            "provenance": project.get("provenance") or "allow",
            "runtime_state": _runtime_state(project, agents, task_state),
            "project_state": _project_state(project, agents, task_state),
            "task_state": ((task_state.get("current") or {}).get("status") or "none"),
            "protocol_state": _protocol_state(project),
            "last_scan": project.get("last_scan"),
            "scan_reason": project.get("scan_reason"),
            "scan_files": project.get("scan_files"),
            "active_operations": project.get("active_operations") or [],
            "agents": agents,
            "task": task_state.get("current") or task_state.get("latest"),
            "task_active": bool(task_state.get("current")),
            "next_action": task_state.get("next_action"),
            "mcp_latency": project.get("mcp_latency") or {},
            "memory_refresh": project.get("memory_refresh") or {"status": "idle"},
        },
        "task_state": task_state,
        "skill_state": skill_state,
        "read_models": _durable_read_models(root, task_state, agents),
        "metrics": {
            "events_24h": metrics_24h["terminal"],
            "failures_24h": metrics_24h["failed"],
            "avg_duration_ms": metrics_24h["avg_duration_ms"],
            "last_event_at": metrics_24h["last_event_at"],
            "operations": metrics_24h["operations"],
            "clients": metrics_24h["clients"],
        },
        "timeline": [
            _event_summary(event, {"key": key, "name": project.get("name") or root.name})
            for event in reversed(terminal)
        ],
    }
