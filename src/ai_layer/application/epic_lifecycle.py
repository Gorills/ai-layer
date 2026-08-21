from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from ai_layer.application.epic_common import (
    append_epic_event,
    audit_payload,
    current_spec,
    epic_for_update,
    epic_payload,
    lock_project,
    project_for_root,
)
from ai_layer.application.epic_spec_editor import apply_spec_edits
from ai_layer.application.work_relations import ensure_epic_root_work
from ai_layer.db.epic_models import Epic, EpicAudit, EpicSpecVersion
from ai_layer.db.models import utcnow
from ai_layer.db.session import session_scope
from ai_layer.epics.contracts import (
    MAX_EPIC_AUDIT_FINDINGS,
    MAX_EPIC_SPEC_CHARS,
    MAX_EPIC_TITLE_CHARS,
    bounded_text,
    epic_key,
    spec_quality,
)


def create(
    project_root: str | Path,
    *,
    title: str,
    spec_markdown: str,
    work_key: str | None = None,
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        lock_project(db, project)
        title_text = bounded_text(title, field="epic title", max_chars=MAX_EPIC_TITLE_CHARS)
        spec_text = bounded_text(
            spec_markdown,
            field="epic spec",
            max_chars=MAX_EPIC_SPEC_CHARS,
        )
        previous = db.scalar(select(func.max(Epic.sequence)).where(Epic.project_id == project.id))
        epic = Epic(project_id=project.id, sequence=int(previous or 0) + 1, title=title_text)
        db.add(epic)
        db.flush()
        root_work = ensure_epic_root_work(
            db,
            project,
            epic,
            create_if_missing=True,
            preferred_work_key=work_key,
        )
        db.add(
            EpicSpecVersion(
                epic_id=epic.id,
                version=1,
                content=spec_text,
                source="draft",
                change_summary="Initial Epic specification created from the accepted discussion context.",
            )
        )
        append_epic_event(
            db,
            project,
            epic,
            "EpicCreated",
            {
                "spec_version": 1,
                "root_work": f"W-{int(root_work.sequence):04d}" if root_work else None,
            },
        )
        db.flush()
        return epic_payload(db, epic, include_spec=True, include_history=True)


def list_for_project(
    project_root: str | Path,
    *,
    include_archived: bool = True,
) -> list[dict]:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        stmt = select(Epic).where(Epic.project_id == project.id)
        if not include_archived:
            stmt = stmt.where(Epic.status != "archived")
        rows = db.scalars(stmt.order_by(Epic.sequence.desc())).all()
        return [
            epic_payload(db, row, include_spec=False, include_history=False, include_audits=False)
            for row in rows
        ]


def get(
    project_root: str | Path,
    *,
    key: str,
    include_history: bool = True,
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        return epic_payload(db, epic, include_spec=True, include_history=include_history)


def get_spec_version(
    project_root: str | Path,
    *,
    key: str,
    version: int | None = None,
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        requested = epic.current_spec_version if version is None else int(version)
        if requested <= 0:
            raise ValueError("version must be a positive integer")
        row = db.scalar(
            select(EpicSpecVersion).where(
                EpicSpecVersion.epic_id == epic.id,
                EpicSpecVersion.version == requested,
            )
        )
        if row is None:
            raise ValueError(f"Epic {key} has no specification version v{requested}")
        return {
            "epic_key": epic_key(epic.sequence),
            "title": epic.title,
            "current_spec_version": epic.current_spec_version,
            "is_current": requested == epic.current_spec_version,
            "spec": {
                "version": row.version,
                "content": row.content,
                "source": row.source,
                "change_summary": row.change_summary,
                "rationale": row.rationale,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            },
        }


def _assert_manual_revision_state(epic: Epic) -> None:
    if epic.status not in {"draft", "approved"}:
        raise RuntimeError(
            "Manual spec revision is allowed only before Phase 0 while Epic is DRAFT/APPROVED; "
            "execution-time reality changes must use epic_reconcile_complete"
        )


def _revision_receipt(
    db,
    epic: Epic,
    *,
    previous_version: int,
    operation: str,
    changed: bool,
    edit_count: int | None = None,
) -> dict:
    payload = epic_payload(db, epic, include_spec=False, include_history=False)
    payload["revision"] = {
        "operation": operation,
        "changed": changed,
        "previous_spec_version": previous_version,
        "current_spec_version": epic.current_spec_version,
        "edit_count": edit_count,
        "next_tool": "epic_next",
    }
    return payload


def _persist_manual_revision(
    db,
    project,
    epic: Epic,
    *,
    content: str,
    source: str,
    change_summary: str,
    rationale: str,
    operation: str,
    edit_count: int | None = None,
) -> dict:
    current = current_spec(db, epic)
    previous_version = int(current.version)
    if content == current.content:
        return _revision_receipt(
            db,
            epic,
            previous_version=previous_version,
            operation=operation,
            changed=False,
            edit_count=edit_count,
        )
    version = epic.current_spec_version + 1
    db.add(
        EpicSpecVersion(
            epic_id=epic.id,
            version=version,
            content=content,
            source=source,
            change_summary=bounded_text(
                change_summary,
                field="change_summary",
                max_chars=4_000,
            ),
            rationale=bounded_text(
                rationale,
                field="rationale",
                max_chars=8_000,
                required=False,
            ),
        )
    )
    epic.current_spec_version = version
    epic.status = "draft"
    epic.blocked_reason = ""
    epic.decision_required = []
    epic.approved_spec_version = None
    epic.execution_spec_version = None
    epic.approved_at = None
    epic.updated_at = utcnow()
    append_epic_event(
        db,
        project,
        epic,
        "EpicSpecRevised",
        {
            "spec_version": version,
            "source": source,
            "operation": operation,
            "edit_count": edit_count,
        },
    )
    db.flush()
    return _revision_receipt(
        db,
        epic,
        previous_version=previous_version,
        operation=operation,
        changed=True,
        edit_count=edit_count,
    )


def revise_spec(
    project_root: str | Path,
    *,
    key: str,
    spec_markdown: str,
    change_summary: str,
    rationale: str = "",
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        _assert_manual_revision_state(epic)
        content = bounded_text(
            spec_markdown,
            field="epic spec",
            max_chars=MAX_EPIC_SPEC_CHARS,
        )
        return _persist_manual_revision(
            db,
            project,
            epic,
            content=content,
            source="revision",
            change_summary=change_summary,
            rationale=rationale,
            operation="full_replace",
        )


def edit_spec(
    project_root: str | Path,
    *,
    key: str,
    expected_spec_version: int,
    edits: list[dict],
    change_summary: str,
    rationale: str = "",
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        _assert_manual_revision_state(epic)
        expected = int(expected_spec_version)
        if expected <= 0:
            raise ValueError("expected_spec_version must be a positive integer")
        if expected != epic.current_spec_version:
            raise RuntimeError(
                f"SPEC_VERSION_CONFLICT: expected v{expected}, current v{epic.current_spec_version}. "
                "Read the current spec and reapply the intended edits."
            )
        current = current_spec(db, epic)
        edited = apply_spec_edits(current.content, edits)
        content = bounded_text(
            edited,
            field="edited epic spec",
            max_chars=MAX_EPIC_SPEC_CHARS,
        )
        return _persist_manual_revision(
            db,
            project,
            epic,
            content=content,
            source="edit",
            change_summary=change_summary,
            rationale=rationale,
            operation="document_edit",
            edit_count=len(edits),
        )


def record_audit(
    project_root: str | Path,
    *,
    key: str,
    summary: str,
    findings: list[dict] | None = None,
    scope: str = "independent",
    auditor_id: str = "",
) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        if epic.status not in {"draft", "approved"}:
            raise RuntimeError(
                "Independent specification audits are allowed before Phase 0 while Epic is DRAFT/APPROVED; "
                "execution-time review belongs to reconciliation/Task review"
            )
        items = list(findings or [])[:MAX_EPIC_AUDIT_FINDINGS]
        row = EpicAudit(
            epic_id=epic.id,
            spec_version=epic.current_spec_version,
            scope=bounded_text(scope, field="audit scope", max_chars=64),
            auditor_id=bounded_text(
                auditor_id,
                field="auditor_id",
                max_chars=128,
                required=False,
            ),
            summary=bounded_text(summary, field="audit summary", max_chars=12_000),
            findings=items,
        )
        db.add(row)
        append_epic_event(
            db,
            project,
            epic,
            "EpicAudited",
            {"spec_version": epic.current_spec_version, "findings": len(items)},
        )
        db.flush()
        return audit_payload(row, current_spec_version=epic.current_spec_version)


def approve(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        if epic.status != "draft":
            raise RuntimeError("Only a DRAFT Epic can be approved")
        quality = spec_quality(current_spec(db, epic).content)
        missing = quality["missing_recommended_sections"]
        if missing:
            raise RuntimeError(
                "Epic spec is missing required human-readable sections: " + ", ".join(missing)
            )
        epic.status = "approved"
        epic.approved_spec_version = epic.current_spec_version
        epic.execution_spec_version = None
        epic.approved_at = utcnow()
        epic.updated_at = utcnow()
        append_epic_event(
            db,
            project,
            epic,
            "EpicApproved",
            {"spec_version": epic.current_spec_version},
        )
        db.flush()
        return epic_payload(db, epic, include_spec=True, include_history=True)


def archive(project_root: str | Path, *, key: str) -> dict:
    with session_scope() as db:
        project = project_for_root(db, project_root)
        epic = epic_for_update(db, project, key)
        if epic.status != "completed":
            raise RuntimeError("Only a mechanically completed Epic may be archived")
        epic.status = "archived"
        epic.archived_at = utcnow()
        epic.updated_at = utcnow()
        append_epic_event(
            db,
            project,
            epic,
            "EpicArchived",
            {"spec_version": epic.execution_spec_version},
        )
        db.flush()
        return epic_payload(db, epic, include_spec=True, include_history=True)
