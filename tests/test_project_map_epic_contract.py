from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import ai_layer.application.epic_navigation as navigation


def test_final_epic_closure_requires_project_map_reconciliation(monkeypatch):
    evidence = {
        "docs_updated": True,
        "knowledge_published": 2,
        "project_map_reconciled": False,
        "project_map_updated": 0,
        "project_map_removed": 0,
        "project_map_scope_paths": [],
        "project_map_no_changes_reason": "",
        "changed_paths": ["docs/README.md"],
    }
    retries = []
    events = []
    monkeypatch.setattr(navigation, "_final_closure_evidence", lambda db, task: evidence)
    monkeypatch.setattr(
        navigation,
        "retry_final_item",
        lambda db, epic, closure: retries.append(dict(closure)),
    )
    monkeypatch.setattr(
        navigation,
        "append_epic_event",
        lambda db, project, epic, event_type, payload: events.append(event_type),
    )
    epic = SimpleNamespace(status="final_review", blocked_reason="", completed_at=None)
    task = SimpleNamespace(sequence=9)
    result = navigation._complete_final_item(object(), object(), epic, task)
    assert result["state"] == "final_retry"
    assert epic.status == "final_review"
    assert retries == [evidence]
    assert events == ["EpicFinalReviewRetryRequired"]


def test_final_epic_closure_accepts_explicit_no_change_map_reconciliation(monkeypatch):
    evidence = {
        "docs_updated": True,
        "knowledge_published": 1,
        "project_map_reconciled": True,
        "project_map_updated": 0,
        "project_map_removed": 0,
        "project_map_scope_paths": ["src/orders/retry.py"],
        "project_map_no_changes_reason": "Affected navigation was verified against current source and remains accurate.",
        "changed_paths": ["docs/README.md", "src/orders/retry.py"],
    }
    events = []
    monkeypatch.setattr(navigation, "_final_closure_evidence", lambda db, task: evidence)
    monkeypatch.setattr(
        navigation,
        "append_epic_event",
        lambda db, project, epic, event_type, payload: events.append((event_type, payload)),
    )
    epic = SimpleNamespace(status="final_review", blocked_reason="", completed_at=None)
    task = SimpleNamespace(sequence=10, id=uuid4())
    result = navigation._complete_final_item(object(), object(), epic, task)
    assert result["state"] == "completed"
    assert epic.status == "completed"
    assert epic.completed_at is not None
    assert events[0][0] == "EpicCompleted"
    assert events[0][1]["project_map_reconciled"] is True
