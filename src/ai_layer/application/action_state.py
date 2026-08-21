from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from typing import Any, NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.action_models import WorkActionState
from ai_layer.db.models import Project, Task, TaskStage, utcnow
from ai_layer.db.work_models import WorkItem
from ai_layer.db.work_relation_models import TaskWorkRelation
from ai_layer.tasks.delegation_contract import worker_job_packet
from ai_layer.work.service import work_key, work_to_dict

CONTRACT_VERSION = 1
TOKEN_VERSION = "act1"
OPEN_TASK_STATUSES = ("active", "blocked")
_TOKEN_RE = re.compile(r"^act1_[A-Za-z0-9_-]{43}$")


class ActionProtocolError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _protocol_error(code: str, message: str) -> NoReturn:
    raise ActionProtocolError(code, message)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def report_fingerprint(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(report)).encode("utf-8")).hexdigest()


def action_token_shape_valid(token: str) -> bool:
    return bool(_TOKEN_RE.fullmatch(str(token or "")))


def _new_action_token() -> str:
    token = f"{TOKEN_VERSION}_{secrets.token_urlsafe(32)}"
    if not action_token_shape_valid(token):  # pragma: no cover - secrets contract guard
        raise RuntimeError("generated action token has an invalid shape")
    return token


def _project_key(project: Project) -> str:
    return str(project.name or project.id)


def _public_assurance(db: Session, work: WorkItem) -> str:
    attached = db.scalar(
        select(TaskWorkRelation.task_id)
        .where(TaskWorkRelation.work_id == work.id, TaskWorkRelation.role == "outcome")
        .limit(1)
    )
    return "reviewed" if attached is not None else "native"


def _public_work(db: Session, work: WorkItem) -> dict[str, Any]:
    return {
        "key": work_key(work),
        "goal": work.goal or None,
        "assurance": _public_assurance(db, work),
        "epic_attached": bool(work.linked_epic_id),
    }


def _state_response(db: Session, project: Project, work: WorkItem, state: WorkActionState) -> dict:
    action: dict[str, Any] = {
        "kind": state.action_kind,
        "action_token": state.action_token,
        "state_version": int(state.state_version),
        "instruction": state.instruction,
    }
    payload = dict(state.payload or {})
    for key in ("worker_kind", "worker", "choices"):
        value = state.worker_kind if key == "worker_kind" else payload.get(key)
        if value not in (None, "", [], {}):
            action[key] = value
    return {
        "contract_version": CONTRACT_VERSION,
        "project": {"key": _project_key(project)},
        "work": _public_work(db, work),
        "next_action": action,
    }


def _finished_response(db: Session, project: Project, work: WorkItem) -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "project": {"key": _project_key(project)},
        "work": _public_work(db, work),
        "next_action": {
            "kind": "done",
            "action_token": None,
            "state_version": 1,
            "instruction": "The durable Work outcome is closed.",
        },
    }


def latest_outcome_task(db: Session, work: WorkItem) -> Task | None:
    open_task = db.scalar(
        select(Task)
        .join(TaskWorkRelation, TaskWorkRelation.task_id == Task.id)
        .where(
            TaskWorkRelation.work_id == work.id,
            TaskWorkRelation.role == "outcome",
            Task.status.in_(OPEN_TASK_STATUSES),
        )
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    if open_task is not None:
        return open_task
    return db.scalar(
        select(Task)
        .join(TaskWorkRelation, TaskWorkRelation.task_id == Task.id)
        .where(
            TaskWorkRelation.work_id == work.id,
            TaskWorkRelation.role == "outcome",
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )


def _worker_kind(stage: TaskStage) -> str:
    if stage.kind in {"review", "discovery"}:
        return "independent_check"
    if stage.kind == "fix":
        return "correction"
    return "change"


def _public_result_contract(contract: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(contract or {})
    allowed = (
        "required",
        "optional",
        "outcomes",
        "verdicts",
        "finding_required_fields",
        "verification_required_fields",
        "findings_to_verify",
    )
    return {key: source[key] for key in allowed if key in source}


def _public_worker_packet(task_payload: Mapping[str, Any], stage: TaskStage) -> dict[str, Any]:
    source = worker_job_packet(
        task_payload.get("delegation_contract")
        if isinstance(task_payload.get("delegation_contract"), dict)
        else None
    )
    packet: dict[str, Any] = {
        "worker_id": stage.worker_id,
        "worker_kind": _worker_kind(stage),
    }
    for key in (
        "goal",
        "acceptance_criteria",
        "constraints",
        "repository_mode",
        "context_policy",
        "requirements",
        "findings_to_verify",
        "open_findings",
        "provenance_notice",
        "discovery_result",
        "risk",
        "agent_policy",
        "project_knowledge_review",
    ):
        value = source.get(key)
        if value not in (None, "", [], {}):
            packet[key] = value
    packet["result_contract"] = _public_result_contract(
        task_payload.get("completion_contract")
        if isinstance(task_payload.get("completion_contract"), dict)
        else None
    )
    return packet


def _state_binding_matches(
    state: WorkActionState,
    *,
    task: Task | None,
    stage: TaskStage | None,
    kind: str,
    worker_kind: str | None,
    worker_id: str,
    state_version: int,
) -> bool:
    return (
        state.task_id == (task.id if task is not None else None)
        and state.stage_id == (stage.id if stage is not None else None)
        and state.action_kind == kind
        and (state.worker_kind or None) == worker_kind
        and (state.worker_id or "") == worker_id
        and int(state.state_version) == int(state_version)
    )


def _upsert_action_state(
    db: Session,
    project: Project,
    work: WorkItem,
    *,
    task: Task | None,
    stage: TaskStage | None,
    kind: str,
    worker_kind: str | None,
    worker_id: str,
    state_version: int,
    instruction: str,
    payload: dict[str, Any] | None = None,
) -> WorkActionState:
    state = db.get(WorkActionState, work.id)
    if state is not None and _state_binding_matches(
        state,
        task=task,
        stage=stage,
        kind=kind,
        worker_kind=worker_kind,
        worker_id=worker_id,
        state_version=state_version,
    ):
        return state
    token = _new_action_token()
    if state is None:
        state = WorkActionState(
            work_id=work.id,
            project_id=project.id,
            state_version=state_version,
            action_kind=kind,
            action_token=token,
        )
        db.add(state)
    state.project_id = project.id
    state.task_id = task.id if task is not None else None
    state.stage_id = stage.id if stage is not None else None
    state.state_version = state_version
    state.action_kind = kind
    state.worker_kind = worker_kind
    state.worker_id = worker_id
    state.action_token = token
    state.instruction = instruction
    state.payload = dict(payload or {})
    state.updated_at = utcnow()
    db.flush()
    return state


def report_checks(report: Mapping[str, Any]) -> list[str]:
    raw = report.get("checks")
    if raw is None:
        raw = report.get("evidence")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def action_debug_snapshot(db: Session, work: WorkItem) -> dict[str, Any]:
    """Test/admin-only compact durable state; never expose raw token binding internals to agents."""
    state = db.get(WorkActionState, work.id)
    return {
        "work": work_to_dict(db, work, include_runs=False, compact=True),
        "action": (
            {
                "state_version": int(state.state_version),
                "kind": state.action_kind,
                "task_id": str(state.task_id) if state.task_id else None,
                "stage_id": str(state.stage_id) if state.stage_id else None,
                "worker_id": state.worker_id or None,
            }
            if state is not None
            else None
        ),
    }
