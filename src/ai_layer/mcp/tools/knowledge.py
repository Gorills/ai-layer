from __future__ import annotations

from ai_layer.application import knowledge as knowledge_uc
from ai_layer.audit.service import mcp_audit
from ai_layer.mcp.runtime import _list, _scoped, _text, core_tool, project_root_for_tool


def knowledge_list(
    status: str = "VERIFIED",
    source_task_id: str | None = None,
    project_root: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Read curated Project Knowledge by lifecycle status; reviewers use DRAFT + source_task_id."""
    root = project_root_for_tool(project_root, tool="knowledge_list")
    wanted = (status or "VERIFIED").strip().upper()
    if wanted not in {"VERIFIED", "DRAFT", "STALE", "SUPERSEDED"}:
        raise ValueError("knowledge_list: status must be VERIFIED|DRAFT|STALE|SUPERSEDED")
    with mcp_audit(root, "knowledge_list", arg_keys=["status", "source_task_id", "project_root", "limit"]):
        return knowledge_uc.list_cards(
            root,
            status=wanted,
            source_task_id=(source_task_id or "").strip() or None,
            limit=max(1, min(int(limit), 200)),
        )


def knowledge_draft_upsert(
    worker_id: str,
    key: str,
    category: str,
    title: str,
    summary: str,
    evidence_paths: list[str] | str,
    claims: list[str] | str | None = None,
    constraints: list[str] | str | None = None,
    unknowns: list[str] | str | None = None,
    project_root: str | None = None,
) -> dict:
    """Write an evidence-backed DRAFT Project Knowledge card; delegated IMPLEMENT/FIX workers only."""
    root = project_root_for_tool(project_root, tool="knowledge_draft_upsert")
    with mcp_audit(
        root,
        "knowledge_draft_upsert",
        arg_keys=[
            "worker_id", "key", "category", "title", "summary", "evidence_paths",
            "claims", "constraints", "unknowns", "project_root",
        ],
    ) as audit:
        result = knowledge_uc.upsert_card_draft(
            root,
            worker_id=_text(worker_id, tool="knowledge_draft_upsert", field="worker_id"),
            key=_text(key, tool="knowledge_draft_upsert", field="key"),
            category=_text(category, tool="knowledge_draft_upsert", field="category"),
            title=_text(title, tool="knowledge_draft_upsert", field="title"),
            summary=_text(summary, tool="knowledge_draft_upsert", field="summary"),
            evidence_paths=_list(evidence_paths),
            claims=_list(claims),
            constraints=_list(constraints),
            unknowns=_list(unknowns),
        )
        audit["metrics"] = {
            "status": result.get("status"),
            "claims": len(result.get("claims") or []),
            "unknowns": len(result.get("unknowns") or []),
            "evidence_paths": len(result.get("source_pointers") or []),
        }
        return _scoped(result, root)


knowledge_list = core_tool()(knowledge_list)
knowledge_draft_upsert = core_tool()(knowledge_draft_upsert)
