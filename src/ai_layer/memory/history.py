from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import Decision, Project, Task
from ai_layer.sessions.service import snapshot_decisions

_TOKEN_RE = re.compile(r"[\w-]{3,}", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {item.casefold() for item in _TOKEN_RE.findall(str(text or ""))}


def _overlap_score(query: str, *values: object) -> float:
    wanted = _tokens(query)
    if not wanted:
        return 0.0
    hay = _tokens("\n".join(str(value or "") for value in values))
    common = len(wanted & hay)
    return common / max(1, min(len(wanted), 8))


def relevant_task_history(db: Session, project: Project, query: str, *, limit: int = 3) -> list[dict]:
    tasks = db.scalars(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "completed")
        .order_by(Task.completed_at.desc(), Task.sequence.desc())
        .limit(100)
    ).all()
    ranked: list[tuple[float, Task]] = []
    for task in tasks:
        changes = dict(task.final_changes or {})
        paths = [
            *list(changes.get("added") or []),
            *list(changes.get("modified") or []),
            *list(changes.get("deleted") or []),
        ]
        score = _overlap_score(
            query,
            task.goal,
            task.completion_summary,
            " ".join(task.acceptance_criteria or []),
            " ".join(task.constraints or []),
            " ".join(paths),
        )
        if score > 0:
            ranked.append((score, task))
    ranked.sort(key=lambda item: (-item[0], -(item[1].sequence or 0)))
    result = []
    for score, task in ranked[: max(1, min(int(limit), 10))]:
        changes = dict(task.final_changes or {})
        paths = [
            *list(changes.get("added") or []),
            *list(changes.get("modified") or []),
            *list(changes.get("deleted") or []),
        ]
        result.append({
            "key": f"T-{int(task.sequence):04d}",
            "goal": task.goal,
            "outcome": task.completion_summary,
            "changed_paths": paths[:20],
            "risk_level": task.risk_level,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "score": round(score, 4),
            "provenance": "ai_layer_task_history",
        })
    return result



def latest_task_summary(db: Session, project: Project) -> dict | None:
    """Compact latest completed task for continuation; never expose internal workflow/reviewer reasoning."""
    task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "completed")
        .order_by(Task.completed_at.desc(), Task.sequence.desc())
        .limit(1)
    )
    if task is None:
        return None
    changes = dict(task.final_changes or {})
    paths = [
        *list(changes.get("added") or []),
        *list(changes.get("modified") or []),
        *list(changes.get("deleted") or []),
    ]
    return {
        "key": f"T-{int(task.sequence):04d}",
        "goal": task.goal,
        "status": task.status,
        "outcome": task.completion_summary,
        "changed_path_count": int(changes.get("total") or len(paths)),
        "changed_paths": paths[:8],
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "handoff_available": bool(task.handoff_session_id),
        "provenance": "ai_layer_task_history_compact",
    }

def relevant_decision_brief(db: Session, project: Project, query: str, *, limit: int = 2) -> list[dict]:
    ranked: list[tuple[float, dict]] = []
    for item in db.scalars(
        select(Decision)
        .where(Decision.project_id == project.id)
        .order_by(Decision.created_at.desc())
        .limit(100)
    ).all():
        score = _overlap_score(query, item.title, item.context, item.decision, item.rationale)
        if score > 0:
            ranked.append((score, {
                "kind": "decision",
                "id": str(item.id),
                "title": item.title,
                "decision": item.decision,
                "rationale": item.rationale,
                "score": round(score, 4),
                "provenance": "ai_layer_decision_history",
            }))
    for item in snapshot_decisions(project, limit=50):
        score = _overlap_score(query, item.get("decision"), item.get("context"))
        if score > 0:
            ranked.append((score, {
                "kind": "session_decision",
                "id": f"session:{item['session_id']}",
                "title": str(item.get("decision") or "")[:120],
                "decision": item.get("decision") or "",
                "rationale": "Committed durable session decision.",
                "score": round(score, 4),
                "provenance": "ai_layer_session_history",
            }))
    ranked.sort(key=lambda item: -item[0])
    result: list[dict] = []
    seen: set[str] = set()
    for _, item in ranked:
        key = str(item.get("decision") or "").casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= max(1, min(int(limit), 8)):
            break
    return result


def knowledge_audit_history(db: Session, project: Project, *, limit: int = 4) -> list[dict]:
    """Return only metadata about prior knowledge work; never previous audit reasoning/outcomes."""
    tasks = db.scalars(
        select(Task)
        .where(Task.project_id == project.id, Task.status == "completed")
        .order_by(Task.completed_at.desc(), Task.sequence.desc())
        .limit(100)
    ).all()
    result: list[dict] = []
    for task in tasks:
        hay = f"{task.goal} {' '.join(task.acceptance_criteria or [])}".casefold()
        if not any(token in hay for token in ("project knowledge", "knowledge", "баз знаний", "база знаний")):
            continue
        result.append({
            "key": f"T-{int(task.sequence):04d}",
            "goal": task.goal,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "provenance": "ai_layer_task_history_metadata_only",
        })
        if len(result) >= max(1, min(int(limit), 10)):
            break
    return result
