from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_layer.application.action_engine import (
    ActionProtocolError,
    continue_action,
    current_action,
    finish_action,
)
from ai_layer.db.base import Base
from ai_layer.db.models import Project
from ai_layer.work.service import begin_work


def test_native_block_resume_then_cancel_stays_server_owned(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = tmp_path / "project"
    root.mkdir()

    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="phase3-native-decision",
            root_path=str(root),
            languages={"python": 1},
            dependencies={},
            architecture_summary="",
            project_intelligence={"legacy": {"level": "low", "score": 0, "signals": []}},
        )
        db.add(project)
        db.commit()
        work, _run = begin_work(
            db,
            project,
            goal="Handle a native engineering blocker",
            observability_coverage="control_plane_only",
        )
        db.commit()

        native = current_action(db, project, work)["next_action"]
        blocked = continue_action(
            db,
            action_token=native["action_token"],
            report={
                "kind": "native_result",
                "summary": "Need a human choice before continuing",
                "outcome": "blocked",
            },
        )["next_action"]
        assert blocked["kind"] == "human_decision"
        assert blocked["choices"] == ["resume", "cancel"]

        resume_report = {
            "kind": "human_choice",
            "summary": "Resume native engineering",
            "selection": "resume",
        }
        resumed_response = continue_action(
            db,
            action_token=blocked["action_token"],
            report=resume_report,
        )
        resumed = resumed_response["next_action"]
        assert resumed["kind"] == "native_engineering"
        assert resumed["state_version"] > blocked["state_version"]
        assert (
            continue_action(db, action_token=blocked["action_token"], report=resume_report)
            == resumed_response
        )
        with pytest.raises(ActionProtocolError, match="IDEMPOTENCY_CONFLICT"):
            continue_action(
                db,
                action_token=blocked["action_token"],
                report={**resume_report, "selection": "cancel"},
            )

        blocked_again = continue_action(
            db,
            action_token=resumed["action_token"],
            report={
                "kind": "native_result",
                "summary": "The external blocker remains",
                "outcome": "blocked",
            },
        )["next_action"]
        cancelled = continue_action(
            db,
            action_token=blocked_again["action_token"],
            report={
                "kind": "human_choice",
                "summary": "Cancel the blocked native work",
                "selection": "cancel",
            },
        )["next_action"]
        assert cancelled["kind"] == "done"

        finished = finish_action(
            db,
            action_token=cancelled["action_token"],
            summary="Cancelled after the blocker could not be resolved",
            status="cancelled",
            map_disposition={"status": "not_applicable", "reason": "No navigation change"},
        )
        assert finished["next_action"]["kind"] == "done"
        assert finished["next_action"]["action_token"] is None
        assert "status" not in finished["work"]
        db.refresh(work)
        assert work.status == "abandoned"
