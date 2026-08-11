from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ai_layer.db.base import Base
from ai_layer.db.models import Project, ReviewFinding, Task, TaskStage, WorkSession
from ai_layer.tasks import service as tasks
from ai_layer.application.tasks import read_state as read_task_state


def _db_project(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    project = Project(
        name="demo",
        root_path=str(root),
        languages={"python": 1},
        dependencies={},
        architecture_summary="",
    )
    db.add(project)
    db.commit()
    return db, project, root


def _complete_bound(db, project, **kwargs):
    current = tasks.current_task(db, project, include_history=False)
    stage = (current.get("task") or {}).get("active_stage") or {}
    if stage.get("id") == kwargs.get("stage_id") and not stage.get("worker_id"):
        tasks.delegate_current_stage(db, project, worker_id=kwargs["worker_id"])
    return tasks.complete_stage(db, project, **kwargs)


def _force_legacy_workflow(db):
    task = db.scalar(select(Task).order_by(Task.created_at.desc()).limit(1))
    assert task is not None
    task.workflow_version = 1
    task.workflow_profile = "legacy_standard"
    db.commit()
    return task


def _complete_implement(db, project, task, root):
    tasks.delegate_current_stage(db, project, worker_id="implementer-1")
    (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    return _complete_bound(
        db,
        project,
        stage_id=task["active_stage"]["id"],
        worker_id="implementer-1",
        summary="Implemented requested behavior and updated focused tests.",
        checks=["focused tests passed"],
    )


def test_legacy_v1_task_pipeline_still_requires_implement_review_fix_review_and_auto_handoff(
    tmp_path: Path,
):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Change application behavior safely",
            acceptance_criteria=["VALUE becomes 2", "review passes"],
            constraints=["preserve public API"],
        )
        assert created["key"] == "T-0001"
        _force_legacy_workflow(db)
        assert created["active_stage"]["kind"] == "implement"

        review1 = _complete_implement(db, project, created, root)
        assert review1["active_stage"]["kind"] == "review"
        assert review1["active_stage"]["review_round"] == 1

        fix1 = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-1",
            summary="Implementation matches the task contract.",
            checks=["pytest focused suite", "manual diff inspection"],
            verdict="pass",
        )
        assert fix1["active_stage"]["kind"] == "fix"
        assert fix1["fix_round"] == 1

        review2 = _complete_bound(
            db,
            project,
            stage_id=fix1["active_stage"]["id"],
            worker_id="fixer-1",
            summary="No review findings; no code changes required.",
            checks=["confirmed clean review result"],
            outcome="no_changes_needed",
        )
        assert review2["active_stage"]["kind"] == "review"
        assert review2["active_stage"]["review_round"] == 2

        completed = _complete_bound(
            db,
            project,
            stage_id=review2["active_stage"]["id"],
            worker_id="reviewer-2",
            summary="Second independent review passed.",
            checks=["pytest focused suite", "manual acceptance inspection"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        assert completed["active_stage"] is None
        assert completed["final_changes"]["modified"] == ["app.py"]
        assert completed["handoff_session_id"]
        assert db.scalar(select(func.count()).select_from(WorkSession)) == 1
        assert tasks.current_task(db, project)["active"] is False
        dashboard = read_task_state(root)
        assert dashboard["current"] is None
        assert dashboard["latest"]["status"] == "completed"
    finally:
        db.close()


def test_review_findings_force_fixer_and_are_verified_by_next_review(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Fix edge case", acceptance_criteria=[], constraints=[]
        )
        review1 = _complete_implement(db, project, created, root)
        fix = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-a",
            summary="Found missing regression coverage.",
            checks=["manual code inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "high",
                    "category": "testing",
                    "path": "app.py",
                    "problem": "Regression path is not covered.",
                    "required_fix": "Add the missing behavior and regression test.",
                }
            ],
        )
        assert fix["active_stage"]["kind"] == "fix"
        assert fix["open_findings"] == 1

        tasks.delegate_current_stage(db, project, worker_id="fixer-a")
        (root / "test_app.py").write_text("def test_value():\n    assert True\n", encoding="utf-8")
        review2 = _complete_bound(
            db,
            project,
            stage_id=fix["active_stage"]["id"],
            worker_id="fixer-a",
            summary="Added regression coverage.",
            checks=["pytest passed"],
        )
        assert review2["active_stage"]["kind"] == "review"
        verify_items = review2["delegation_contract"]["findings_to_verify"]
        assert len(verify_items) == 1
        assert verify_items[0]["status"] == "pending_verification"

        completed = _complete_bound(
            db,
            project,
            stage_id=review2["active_stage"]["id"],
            worker_id="reviewer-b",
            summary="Regression fix verified.",
            checks=["pytest passed", "manual diff inspection"],
            verdict="pass",
            verification_results=[
                {
                    "finding_id": verify_items[0]["id"],
                    "status": "verified",
                    "evidence": "Regression behavior is covered and pytest passed.",
                }
            ],
        )
        assert completed["status"] == "completed"
        finding = db.scalar(select(ReviewFinding))
        assert finding is not None and finding.status == "verified"
        handoff = db.scalar(
            select(WorkSession).where(WorkSession.id == UUID(completed["handoff_session_id"]))
        )
        assert handoff is not None
        assert any("Regression path is not covered" in item for item in handoff.notable_findings)
    finally:
        db.close()


def test_second_open_task_is_rejected(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="First", acceptance_criteria=[], constraints=[])
        with pytest.raises(RuntimeError, match="Sequential execution forbids a second task"):
            tasks.create_task(db, project, goal="Second", acceptance_criteria=[], constraints=[])
        assert db.scalar(select(func.count()).select_from(Task)) == 1
    finally:
        db.close()


def test_worker_identity_cannot_be_reused_across_stages(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(db, project, goal="One", acceptance_criteria=[], constraints=[])
        review = _complete_implement(db, project, created, root)
        with pytest.raises(ValueError, match="already used"):
            _complete_bound(
                db,
                project,
                stage_id=review["active_stage"]["id"],
                worker_id="implementer-1",
                summary="Review attempted with reused worker.",
                checks=["manual inspection"],
                verdict="pass",
            )
    finally:
        db.close()


def test_reviewer_write_blocks_task_until_repository_is_restored(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(db, project, goal="One", acceptance_criteria=[], constraints=[])
        review = _complete_implement(db, project, created, root)
        expected = (root / "app.py").read_text(encoding="utf-8")
        tasks.delegate_current_stage(db, project, worker_id="reviewer-write")
        (root / "app.py").write_text("VALUE = 999\n", encoding="utf-8")

        blocked = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-write",
            summary="Reviewer accidentally edited code.",
            checks=["manual inspection"],
            verdict="pass",
        )
        assert blocked["status"] == "blocked"
        assert "modified repository files" in blocked["blocked_reason"]
        invalid = db.scalar(
            select(TaskStage).where(
                TaskStage.task_id == UUID(created["id"]), TaskStage.status == "invalid"
            )
        )
        assert invalid is not None

        with pytest.raises(RuntimeError, match="still differs"):
            tasks.resume_task(db, project)

        (root / "app.py").write_text(expected, encoding="utf-8")
        resumed = tasks.resume_task(db, project)
        assert resumed["status"] == "active"
        assert resumed["active_stage"]["kind"] == "review"
        assert resumed["active_stage"]["id"] != review["active_stage"]["id"]
    finally:
        db.close()


def test_clean_review_fixer_cannot_introduce_unrelated_changes(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(db, project, goal="One", acceptance_criteria=[], constraints=[])
        _force_legacy_workflow(db)
        review = _complete_implement(db, project, created, root)
        fix = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-clean",
            summary="Clean review.",
            checks=["manual inspection"],
            verdict="pass",
        )
        tasks.delegate_current_stage(db, project, worker_id="fixer-surprise")
        (root / "surprise.py").write_text("BAD = True\n", encoding="utf-8")
        blocked = _complete_bound(
            db,
            project,
            stage_id=fix["active_stage"]["id"],
            worker_id="fixer-surprise",
            summary="Changed unrelated code despite no findings.",
            checks=["none needed"],
            outcome="done",
        )
        assert blocked["status"] == "blocked"
        assert "no findings" in blocked["blocked_reason"]
    finally:
        db.close()


def test_task_baseline_reuses_fresh_memory_content_hash(tmp_path: Path, monkeypatch):
    db, project, root = _db_project(tmp_path)
    try:
        source = root / "app.py"
        stat = source.stat()
        import hashlib

        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        memory_dir = root / ".ai-layer" / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "file_state.json").write_text(
            __import__("json").dumps(
                {
                    "app.py": {
                        "content_sha256": expected,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "ctime_ns": stat.st_ctime_ns,
                    }
                }
            ),
            encoding="utf-8",
        )
        original_hash = tasks._hash_file
        hashed = []

        def tracking_hash(path):
            hashed.append(path.name)
            return original_hash(path)

        monkeypatch.setattr(tasks, "_hash_file", tracking_hash)
        tasks.create_task(
            db, project, goal="Reuse memory hash", acceptance_criteria=[], constraints=[]
        )
        assert "app.py" not in hashed
    finally:
        db.close()


def test_completed_stage_requires_verification_check(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Verify stage", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="implementer-no-checks")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="requires at least one verification check"):
            _complete_bound(
                db,
                project,
                stage_id=created["active_stage"]["id"],
                worker_id="implementer-no-checks",
                summary="Implementation attempted without verification.",
                checks=[],
            )
    finally:
        db.close()


def test_unexpected_clean_fixer_changes_must_be_reverted_before_resume(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(db, project, goal="One", acceptance_criteria=[], constraints=[])
        _force_legacy_workflow(db)
        review = _complete_implement(db, project, created, root)
        fix = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-clean-resume",
            summary="Clean review.",
            checks=["manual inspection"],
            verdict="pass",
        )
        expected = (root / "app.py").read_text(encoding="utf-8")
        tasks.delegate_current_stage(db, project, worker_id="fixer-unexpected-resume")
        (root / "surprise.py").write_text("BAD = True\n", encoding="utf-8")
        blocked = _complete_bound(
            db,
            project,
            stage_id=fix["active_stage"]["id"],
            worker_id="fixer-unexpected-resume",
            summary="Unexpected change.",
            checks=["manual inspection"],
        )
        assert blocked["status"] == "blocked"

        with pytest.raises(RuntimeError, match="unauthorized repository changes"):
            tasks.resume_task(db, project)

        (root / "surprise.py").unlink()
        assert (root / "app.py").read_text(encoding="utf-8") == expected
        resumed = tasks.resume_task(db, project)
        assert resumed["status"] == "active"
        assert resumed["active_stage"]["kind"] == "fix"
    finally:
        db.close()


def test_rejected_stage_report_does_not_consume_worker_or_stage(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Retry report", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="implementer-retry")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        stage_id = created["active_stage"]["id"]
        with pytest.raises(ValueError, match="requires at least one verification check"):
            _complete_bound(
                db,
                project,
                stage_id=stage_id,
                worker_id="implementer-retry",
                summary="Missing checks.",
                checks=[],
            )
        runtime = tasks.current_task(db, project)
        assert runtime["task"]["active_stage"]["id"] == stage_id
        assert runtime["task"]["active_stage"]["worker_id"] == "implementer-retry"

        advanced = _complete_bound(
            db,
            project,
            stage_id=stage_id,
            worker_id="implementer-retry",
            summary="Now with verification.",
            checks=["focused test passed"],
        )
        assert advanced["active_stage"]["kind"] == "review"
    finally:
        db.close()


def test_review_submission_normalizes_weak_model_aliases_and_pass_with_findings(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Normalize review contract", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)

        result = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-normalized",
            summary="Found one actionable issue.",
            checks=["manual diff inspection"],
            verdict="pass",
            findings=[
                {
                    "severity": "warning",
                    "file": "app.py",
                    "issue": "Weak-model alias should be accepted without a retry.",
                    "fix": "Correct the implementation before the next review.",
                }
            ],
        )

        assert result["status"] == "active"
        assert result["active_stage"]["kind"] == "fix"
        assert result["effective_review_verdict"] == "changes_required"
        normalizations = result["input_normalizations"]
        assert "verdict:pass->changes_required(findings_present)" in normalizations
        assert "finding[1].issue->problem" in normalizations
        assert "finding[1].file->path" in normalizations
        assert "finding[1].fix->required_fix" in normalizations
        assert "finding[1].severity:warning->medium" in normalizations
        finding = db.scalar(select(ReviewFinding))
        assert finding is not None
        assert finding.problem == "Weak-model alias should be accepted without a retry."
        assert finding.path == "app.py"
        assert finding.severity == "medium"
    finally:
        db.close()


def test_review_fail_alias_becomes_changes_required():
    verdict, findings, normalizations = tasks._normalize_review_submission(
        "fail",
        [{"message": "A real defect remains."}],
    )
    assert verdict == "changes_required"
    assert findings[0]["problem"] == "A real defect remains."
    assert "verdict:fail->changes_required" in normalizations


def test_review_cannot_blanket_pass_pending_findings_without_per_finding_evidence(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Verify finding", acceptance_criteria=[], constraints=[]
        )
        review1 = _complete_implement(db, project, created, root)
        fix = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-x",
            summary="Found issue.",
            checks=["inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "medium",
                    "category": "code",
                    "path": "app.py",
                    "problem": "Behavior needs verification.",
                    "required_fix": "Fix it.",
                }
            ],
        )
        tasks.delegate_current_stage(db, project, worker_id="fixer-x")
        (root / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        review2 = _complete_bound(
            db,
            project,
            stage_id=fix["active_stage"]["id"],
            worker_id="fixer-x",
            summary="Applied fix.",
            checks=["focused tests passed"],
        )
        with pytest.raises(ValueError, match="verification_results"):
            _complete_bound(
                db,
                project,
                stage_id=review2["active_stage"]["id"],
                worker_id="reviewer-y",
                summary="Looks fixed.",
                checks=["inspection"],
                verdict="pass",
            )
    finally:
        db.close()


def test_still_open_verification_forces_another_fix_round(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Keep unresolved finding open", acceptance_criteria=[], constraints=[]
        )
        review1 = _complete_implement(db, project, created, root)
        fix = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-open",
            summary="Found issue.",
            checks=["inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "high",
                    "category": "code",
                    "path": "app.py",
                    "problem": "Issue remains.",
                    "required_fix": "Correct it.",
                }
            ],
        )
        finding_id = fix["findings"][0]["id"]
        tasks.delegate_current_stage(db, project, worker_id="fixer-open")
        (root / "app.py").write_text("VALUE = 4\n", encoding="utf-8")
        review2 = _complete_bound(
            db,
            project,
            stage_id=fix["active_stage"]["id"],
            worker_id="fixer-open",
            summary="Attempted fix.",
            checks=["focused tests"],
        )
        result = _complete_bound(
            db,
            project,
            stage_id=review2["active_stage"]["id"],
            worker_id="reviewer-open-2",
            summary="Issue is still reproducible.",
            checks=["reproduction"],
            verdict="pass",
            verification_results=[
                {
                    "finding_id": finding_id,
                    "status": "still_open",
                    "evidence": "Focused reproduction still fails on the original edge case.",
                }
            ],
        )
        assert result["active_stage"]["kind"] == "fix"
        finding = db.get(ReviewFinding, UUID(finding_id))
        assert finding.status == "open"
        assert "still fails" in finding.verification_evidence
        assert finding.verification_history[-1]["status"] == "still_open"
        assert finding.verification_history[-1]["stage_id"] == review2["active_stage"]["id"]
    finally:
        db.close()


def test_task_dashboard_prefers_canonical_database_over_stale_disk(tmp_path: Path, monkeypatch):
    from contextlib import contextmanager
    from ai_layer.application import tasks as application_tasks

    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Canonical dashboard state", acceptance_criteria=[], constraints=[]
        )
        state_root = tasks._task_root(project)
        tasks._atomic_write_json(
            state_root / "current.json", {"status": "stale", "id": "disk-only"}
        )
        tasks._atomic_write_json(state_root / "latest.json", {"status": "stale", "id": "disk-only"})

        @contextmanager
        def fake_scope():
            yield db

        monkeypatch.setattr(application_tasks, "session_scope", fake_scope)
        dashboard = read_task_state(root)
        assert dashboard["source"] == "database"
        assert dashboard["current"]["id"] == created["id"]
        assert dashboard["current"]["status"] == "active"
        assert dashboard["current"]["id"] != "disk-only"
    finally:
        db.close()


def test_automatic_remediation_stops_for_human_attention_and_resume_is_explicit(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Bound remediation", acceptance_criteria=[], constraints=[]
        )
        review1 = _complete_implement(db, project, created, root)
        fix1 = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-limit-1",
            summary="Issue found.",
            checks=["manual inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "high",
                    "category": "correctness",
                    "path": "app.py",
                    "problem": "Persistent defect.",
                    "required_fix": "Fix the defect.",
                }
            ],
        )
        review2 = _complete_bound(
            db,
            project,
            stage_id=fix1["active_stage"]["id"],
            worker_id="fixer-limit-1",
            summary="Attempted first remediation.",
            checks=["focused tests"],
        )
        pending1 = review2["delegation_contract"]["findings_to_verify"][0]
        fix2 = _complete_bound(
            db,
            project,
            stage_id=review2["active_stage"]["id"],
            worker_id="reviewer-limit-2",
            summary="Issue still present.",
            checks=["manual inspection"],
            verdict="changes_required",
            verification_results=[
                {
                    "finding_id": pending1["id"],
                    "status": "still_open",
                    "evidence": "The defect is still visible in app.py.",
                }
            ],
        )
        assert fix2["active_stage"]["kind"] == "fix"
        assert fix2["fix_round"] == 2

        review3 = _complete_bound(
            db,
            project,
            stage_id=fix2["active_stage"]["id"],
            worker_id="fixer-limit-2",
            summary="Attempted second remediation.",
            checks=["focused tests"],
        )
        pending2 = review3["delegation_contract"]["findings_to_verify"][0]
        stopped = _complete_bound(
            db,
            project,
            stage_id=review3["active_stage"]["id"],
            worker_id="reviewer-limit-3",
            summary="Still not acceptable.",
            checks=["manual inspection"],
            verdict="changes_required",
            verification_results=[
                {
                    "finding_id": pending2["id"],
                    "status": "still_open",
                    "evidence": "The same defect remains after two remediation attempts.",
                }
            ],
        )
        assert stopped["status"] == "blocked"
        assert stopped["active_stage"] is None
        assert stopped["human_attention_required"] is True
        assert stopped["next_action"]["action"] == "human_attention_required"
        assert stopped["fix_round"] == 2

        resumed = tasks.resume_task(db, project)
        assert resumed["status"] == "active"
        assert resumed["active_stage"]["kind"] == "fix"
        assert resumed["fix_round"] == 3
    finally:
        db.close()


def test_duplicate_finding_reuses_id_instead_of_growing_active_workset(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Deduplicate findings", acceptance_criteria=[], constraints=[]
        )
        review1 = _complete_implement(db, project, created, root)
        first = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-dedupe-1",
            summary="Found one issue.",
            checks=["inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "medium",
                    "category": "testing",
                    "path": "app.py",
                    "problem": "Missing edge-case coverage.",
                    "required_fix": "Add coverage.",
                }
            ],
        )
        finding_id = first["active_findings"][0]["id"]
        review2 = _complete_bound(
            db,
            project,
            stage_id=first["active_stage"]["id"],
            worker_id="fixer-dedupe-1",
            summary="Attempted fix.",
            checks=["pytest"],
        )
        result = _complete_bound(
            db,
            project,
            stage_id=review2["active_stage"]["id"],
            worker_id="reviewer-dedupe-2",
            summary="Same issue remains.",
            checks=["inspection"],
            verdict="changes_required",
            verification_results=[
                {
                    "finding_id": finding_id,
                    "status": "still_open",
                    "evidence": "Coverage is still absent.",
                }
            ],
            findings=[
                {
                    "severity": "high",
                    "category": "testing",
                    "path": "app.py",
                    "problem": "  Missing   edge-case coverage. ",
                    "required_fix": "Add regression coverage.",
                }
            ],
        )
        assert result["finding_summary"]["total"] == 1
        assert result["open_findings"] == 1
        assert result["active_findings"][0]["id"] == finding_id
        assert result["active_findings"][0]["severity"] == "high"
        assert db.scalar(select(func.count()).select_from(ReviewFinding)) == 1
    finally:
        db.close()


def test_cancel_is_idempotent_after_transport_retry(tmp_path: Path):
    db, project, _ = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="Cancel safely", acceptance_criteria=[], constraints=[])
        first = tasks.cancel_task(db, project, reason="User stopped the run.")
        second = tasks.cancel_task(db, project, reason="Retry after transport closed.")
        assert first["status"] == "cancelled"
        assert second["status"] == "cancelled"
        assert second["idempotent"] is True
    finally:
        db.close()


def test_review_sandbox_runs_writing_check_without_touching_canonical_repo(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core.config import get_settings

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Sandbox checks", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-sandbox")
        prepared = tasks.prepare_current_review_sandbox(db, project)
        sandbox = Path(prepared["path"])
        assert sandbox.exists()
        assert root.resolve() not in sandbox.resolve().parents

        check = tasks.run_current_review_check(
            db,
            project,
            command=[
                "python",
                "-c",
                "from pathlib import Path; Path('review-artifact.tmp').write_text('ok')",
            ],
            timeout_seconds=30,
        )
        assert check["ok"] is True
        assert (sandbox / "review-artifact.tmp").exists()
        assert not (root / "review-artifact.tmp").exists()

        next_stage = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-sandbox",
            summary="Sandboxed executable check passed.",
            checks=[],
            verdict="pass",
        )
        completed_review = next(
            item for item in next_stage["stages"] if item["id"] == review["active_stage"]["id"]
        )
        assert (
            completed_review["check_evidence_assurance"]
            == "ai-layer-executed-sandbox+reported-by-worker"
        )
        assert any(
            str(item).startswith("[ai-layer-sandbox] PASS") for item in completed_review["checks"]
        )
        assert not sandbox.exists()
    finally:
        db.close()
        get_settings.cache_clear()


def test_review_sandbox_failed_check_prevents_pass_until_successful_rerun(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core.config import get_settings

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Sandbox failure gate", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-sandbox-fail")
        retry_code = "from pathlib import Path; p=Path('retry.marker'); existed=p.exists(); p.write_text('x'); raise SystemExit(0 if existed else 3)"
        failed = tasks.run_current_review_check(
            db, project, command=["python", "-c", retry_code], timeout_seconds=30
        )
        assert failed["ok"] is False
        with pytest.raises(ValueError, match="sandbox verification check is failing"):
            _complete_bound(
                db,
                project,
                stage_id=review["active_stage"]["id"],
                worker_id="reviewer-sandbox-fail",
                summary="Should not pass.",
                checks=[],
                verdict="pass",
            )
        succeeded = tasks.run_current_review_check(
            db, project, command=["python", "-c", retry_code], timeout_seconds=30
        )
        assert succeeded["ok"] is True
        result = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-sandbox-fail",
            summary="Corrected check passed.",
            checks=[],
            verdict="pass",
        )
        assert result["status"] == "completed"
        assert result["active_stage"] is None
    finally:
        db.close()
        get_settings.cache_clear()


def test_review_delegation_contract_is_context_isolated(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Review isolation", acceptance_criteria=["safe"], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        contract = review["delegation_contract"]
        assert contract["context_policy"]["mode"] == "isolated_review"
        assert "implementer/fixer self-assessment" in contract["context_policy"]["exclude"]
        assert "Implemented requested behavior" not in str(contract)
        assert contract["findings_to_verify"] == []
    finally:
        db.close()


def test_clean_noop_fixer_does_not_consume_remediation_budget(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="No-op budget", acceptance_criteria=[], constraints=[]
        )
        _force_legacy_workflow(db)
        review1 = _complete_implement(db, project, created, root)
        clean_fix = _complete_bound(
            db,
            project,
            stage_id=review1["active_stage"]["id"],
            worker_id="reviewer-noop-budget",
            summary="Clean first review.",
            checks=["inspection"],
            verdict="pass",
        )
        review2 = _complete_bound(
            db,
            project,
            stage_id=clean_fix["active_stage"]["id"],
            worker_id="fixer-noop-budget",
            summary="No changes needed.",
            checks=["confirmed"],
            outcome="no_changes_needed",
        )
        assert review2["automatic_remediation_count"] == 0
        real_fix1 = _complete_bound(
            db,
            project,
            stage_id=review2["active_stage"]["id"],
            worker_id="reviewer-after-noop",
            summary="Found a later defect.",
            checks=["inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "medium",
                    "category": "correctness",
                    "path": "app.py",
                    "problem": "Later defect.",
                    "required_fix": "Fix it.",
                }
            ],
        )
        assert real_fix1["status"] == "active"
        assert real_fix1["active_stage"]["kind"] == "fix"
        assert real_fix1["automatic_remediation_count"] == 0
    finally:
        db.close()


def test_review_sandbox_durable_evidence_excludes_output_and_redacts_secret_args(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core.config import get_settings
    from ai_layer.tasks.sandbox import review_check_evidence

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Private sandbox evidence", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-private-sandbox")
        check = tasks.run_current_review_check(
            db,
            project,
            command=[
                "python",
                "-c",
                "print('API_TOKEN=supersecretvalue')",
                "--token",
                "anothersecretvalue",
            ],
            timeout_seconds=30,
        )
        assert "supersecretvalue" not in check["stdout_tail"]
        assert check["command"][-1] == "<redacted>"

        task_row = db.scalar(select(Task).where(Task.id == UUID(created["id"])))
        stage_row = db.scalar(
            select(TaskStage).where(TaskStage.id == UUID(review["active_stage"]["id"]))
        )
        records = review_check_evidence(project, task_row, stage_row)
        assert len(records) == 1
        assert "stdout_tail" not in records[0]
        assert "stderr_tail" not in records[0]
        assert "supersecretvalue" not in str(records[0])
        assert "anothersecretvalue" not in str(records[0])
    finally:
        db.close()
        get_settings.cache_clear()


def test_review_sandbox_does_not_inherit_host_secret_environment_and_scrubs_secret_argv(
    tmp_path: Path, monkeypatch
):
    from ai_layer.core.config import get_settings

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    monkeypatch.setenv("MY_SECRET_TOKEN", "host-secret-value-123")
    get_settings.cache_clear()
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Sandbox env isolation", acceptance_criteria=[], constraints=[]
        )
        _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-env-isolation")
        env_check = tasks.run_current_review_check(
            db,
            project,
            command=[
                "python",
                "-c",
                "import os; print(os.environ.get('MY_SECRET_TOKEN', '<missing>'))",
            ],
            timeout_seconds=30,
        )
        assert env_check["ok"] is True
        assert "host-secret-value-123" not in env_check["stdout_tail"]
        assert "<missing>" in env_check["stdout_tail"]

        argv_check = tasks.run_current_review_check(
            db,
            project,
            command=[
                "python",
                "-c",
                "import sys; print(sys.argv[-1])",
                "--token",
                "argv-secret-value-456",
            ],
            timeout_seconds=30,
        )
        assert argv_check["ok"] is True
        assert "argv-secret-value-456" not in argv_check["stdout_tail"]
        assert "<redacted>" in argv_check["stdout_tail"]
    finally:
        db.close()
        get_settings.cache_clear()


def test_review_sandbox_does_not_inherit_python_import_overrides(tmp_path: Path, monkeypatch):
    from ai_layer.core.config import get_settings

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    monkeypatch.setenv("PYTHONPATH", "/host/canonical/source")
    monkeypatch.setenv("PYTHONHOME", "/host/python-home")
    get_settings.cache_clear()
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Sandbox import isolation", acceptance_criteria=[], constraints=[]
        )
        _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-import-isolation")
        check = tasks.run_current_review_check(
            db,
            project,
            command=[
                "python",
                "-c",
                "import os; print(os.environ.get('PYTHONPATH', '<missing>')); print(os.environ.get('PYTHONHOME', '<missing>'))",
            ],
            timeout_seconds=30,
        )
        assert check["ok"] is True
        assert "/host/canonical/source" not in check["stdout_tail"]
        assert "/host/python-home" not in check["stdout_tail"]
        assert check["stdout_tail"].count("<missing>") == 2
    finally:
        db.close()
        get_settings.cache_clear()


def test_compact_task_recovery_excludes_completed_worker_summaries(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Compact review context", acceptance_criteria=[], constraints=[]
        )
        _complete_implement(db, project, created, root)
        compact = tasks.current_task(db, project, include_history=False)
        payload = compact["task"]
        assert payload["active_stage"]["kind"] == "review"
        assert len(payload["stages"]) == 1
        assert payload["stages"][0]["kind"] == "review"
        assert "Implemented requested behavior" not in str(payload)
    finally:
        db.close()


def test_review_sandbox_uses_git_worktree_and_overlays_dirty_worktree(tmp_path: Path, monkeypatch):
    import json
    import shutil
    import subprocess
    from ai_layer.core.config import get_settings

    git = shutil.which("git")
    if not git:
        pytest.skip("git is required for worktree-mode acceptance")

    monkeypatch.setenv("AI_LAYER_HOME", str(tmp_path / "ai-home"))
    get_settings.cache_clear()
    db, project, root = _db_project(tmp_path)
    try:
        subprocess.run([git, "-C", str(root), "init", "-q"], check=True)
        subprocess.run(
            [git, "-C", str(root), "config", "user.email", "test@example.invalid"], check=True
        )
        subprocess.run([git, "-C", str(root), "config", "user.name", "AI Layer Test"], check=True)
        subprocess.run([git, "-C", str(root), "add", "app.py"], check=True)
        subprocess.run([git, "-C", str(root), "commit", "-qm", "baseline"], check=True)
        (root / ".gitignore").write_text(".env\nnode_modules/\n.venv/\n", encoding="utf-8")
        subprocess.run([git, "-C", str(root), "add", ".gitignore"], check=True)
        subprocess.run(
            [git, "-C", str(root), "commit", "-qm", "ignore generated files"], check=True
        )
        (root / ".env").write_text("TOKEN=do-not-copy\n", encoding="utf-8")
        (root / "node_modules" / "pkg").mkdir(parents=True)
        (root / "node_modules" / "pkg" / "index.js").write_text(
            "module.exports = 1\n", encoding="utf-8"
        )
        (root / ".venv" / "bin").mkdir(parents=True)
        (root / ".venv" / "bin" / "python").write_text("ignored\n", encoding="utf-8")

        created = tasks.create_task(
            db, project, goal="Git worktree review", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="reviewer-git-worktree")
        prepared = tasks.prepare_current_review_sandbox(db, project)
        sandbox = Path(prepared["path"])
        manifest = json.loads(
            (sandbox / ".ai-layer-review-sandbox.json").read_text(encoding="utf-8")
        )
        assert manifest["mode"] == "git-worktree"
        assert (sandbox / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        assert not (sandbox / ".env").exists()
        assert not (sandbox / "node_modules").exists()
        assert not (sandbox / ".venv").exists()

        check = tasks.run_current_review_check(
            db,
            project,
            command=["python", "-c", "from pathlib import Path; Path('cache.tmp').write_text('x')"],
            timeout_seconds=30,
        )
        assert check["ok"] is True
        assert (sandbox / "cache.tmp").exists()
        assert not (root / "cache.tmp").exists()

        _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-git-worktree",
            summary="Git worktree sandbox check passed.",
            checks=[],
            verdict="pass",
        )
        assert not sandbox.exists()
        worktrees = subprocess.run(
            [git, "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert str(sandbox) not in worktrees
    finally:
        db.close()
        get_settings.cache_clear()


def _init_git_repo(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)


def test_task_adopt_records_unmanaged_git_changes_and_starts_at_review(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        (root / "app.py").write_text("VALUE = 9\n", encoding="utf-8")
        (root / "new.txt").write_text("outside task layer\n", encoding="utf-8")

        adopted = tasks.adopt_task(
            db,
            project,
            goal="Review work that was performed outside Task Layer",
            acceptance_criteria=["implementation is safe"],
            constraints=[],
        )

        assert adopted["execution_origin"] == "adopted_unmanaged_changes"
        assert adopted["active_stage"]["kind"] == "review"
        assert adopted["active_stage"]["review_round"] == 1
        assert adopted["adopted_changes"]["total"] == 2
        assert set(adopted["adopted_changes"]["paths"]) == {"app.py", "new.txt"}
        assert "original implementation" in adopted["delegation_contract"]["provenance_notice"]
        assert (
            db.scalar(
                select(func.count()).select_from(TaskStage).where(TaskStage.kind == "implement")
            )
            == 0
        )
    finally:
        db.close()


def test_task_adopt_clean_git_tree_is_rejected_instead_of_inventing_history(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        with pytest.raises(
            RuntimeError, match="found no staged, unstaged, or untracked Git changes"
        ):
            tasks.adopt_task(
                db,
                project,
                goal="Nothing to adopt",
                acceptance_criteria=[],
                constraints=[],
            )
        assert db.scalar(select(func.count()).select_from(Task)) == 0
    finally:
        db.close()


def test_task_adopt_non_git_project_fails_closed(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        (root / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="requires a Git repository"):
            tasks.adopt_task(
                db,
                project,
                goal="Cannot prove unmanaged delta",
                acceptance_criteria=[],
                constraints=[],
            )
    finally:
        db.close()


def test_adopted_task_handoff_never_claims_managed_implementation(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        (root / "app.py").write_text("VALUE = 7\n", encoding="utf-8")
        adopted = tasks.adopt_task(
            db,
            project,
            goal="Validate unmanaged change",
            acceptance_criteria=["review passes"],
            constraints=[],
        )
        completed = _complete_bound(
            db,
            project,
            stage_id=adopted["active_stage"]["id"],
            worker_id="reviewer-adopt-1",
            summary="Adopted change is correct.",
            checks=["manual inspection"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        assert completed["execution_origin"] == "adopted_unmanaged_changes"
        assert completed["final_changes"]["total"] == 0
        handoff = db.scalar(
            select(WorkSession).where(WorkSession.id == UUID(completed["handoff_session_id"]))
        )
        assert handoff is not None
        assert "no managed implementation stage was claimed" in handoff.current_state
        assert any(
            "did not claim the original implementation stage" in fact
            for fact in handoff.verified_facts
        )
    finally:
        db.close()


def test_task_next_is_authoritative_navigator_and_stage_specific_completion_avoids_ids(
    tmp_path: Path,
):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Guided workflow", acceptance_criteria=[], constraints=[]
        )
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "delegate_stage"
        assert nav["next_action"]["tool"] == "task_stage_delegate"
        assert nav["task"]["active_stage"]["worker_id"] is None

        delegated = tasks.delegate_current_stage(db, project, worker_id="guided-implementer")
        assert delegated["active_stage"]["worker_id"] == "guided-implementer"
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "record_stage_result"
        assert nav["next_action"]["tool"] == "task_implementation_complete"
        assert nav["task"]["completion_contract"]["required"] == ["summary", "checks"]

        (root / "app.py").write_text("VALUE = 8\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Implemented through the bound worker.",
            checks=["focused test passed"],
        )
        assert review["active_stage"]["kind"] == "review"
        assert review["active_stage"]["worker_id"] is None
        assert tasks.next_task_action(db, project)["next_action"]["tool"] == "task_stage_delegate"
    finally:
        db.close()


def test_undelegated_repository_mutation_is_detected_before_worker_binding(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(db, project, goal="Catch bypass", acceptance_criteria=[], constraints=[])
        (root / "app.py").write_text("VALUE = 99\n", encoding="utf-8")
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "unmanaged_stage_mutation"
        assert nav["next_action"]["code"] == "UNMANAGED_STAGE_MUTATION"
        assert nav["task"]["undelegated_changes"]["modified"] == ["app.py"]
        with pytest.raises(RuntimeError, match="UNMANAGED_STAGE_MUTATION"):
            tasks.delegate_current_stage(db, project, worker_id="late-implementer")
    finally:
        db.close()


def test_task_create_accepts_unknown_dirty_git_worktree_as_captured_baseline(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        (root / "app.py").write_text("VALUE = 41\n", encoding="utf-8")
        nav = tasks.next_task_action(db, project)
        assert nav["state"] == "idle_with_preexisting_changes"
        assert nav["next_action"]["action"] == "create_task"
        assert nav["preexisting_changes"]["paths"] == ["app.py"]
        assert "Do not stash/reset/restore/commit" in nav["next_action"]["message"]

        created = tasks.create_task(
            db,
            project,
            goal="Start safely over existing unrelated work",
            acceptance_criteria=[],
            constraints=[],
        )
        assert created["execution_origin"] == "managed"
        assert created["preexisting_changes"]["total"] == 1
        assert created["preexisting_changes"]["paths"] == ["app.py"]
        assert "immutable baseline" in created["delegation_contract"]["provenance_notice"]
    finally:
        db.close()


def test_dirty_baseline_excludes_preexisting_unrelated_work_from_task_delta(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        (root / "other.py").write_text("OTHER = 1\n", encoding="utf-8")
        import subprocess

        subprocess.run(["git", "-C", str(root), "add", "other.py"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "add other"], check=True)
        (root / "app.py").write_text("VALUE = 41\n", encoding="utf-8")  # unrelated pre-existing WIP

        created = tasks.create_task(
            db, project, goal="Change only other.py", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="dirty-baseline-impl")
        (root / "other.py").write_text("OTHER = 2\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Changed target file.",
            checks=["focused check"],
        )
        assert review["active_stage"]["kind"] == "review"
        tasks.delegate_current_stage(db, project, worker_id="dirty-baseline-review")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="review",
            summary="Reviewed task delta.",
            checks=["inspection"],
            verdict="pass",
        )
        assert completed["final_changes"]["modified"] == ["other.py"]
        assert "app.py" not in completed["final_changes"]["modified"]
        assert completed["preexisting_changes"]["paths"] == ["app.py"]
    finally:
        db.close()


def test_dirty_baseline_same_file_is_task_delta_and_micro_escalates_to_review(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        (root / "app.py").write_text("VALUE = 41\n", encoding="utf-8")
        created = tasks.create_task(
            db,
            project,
            goal="Tiny follow-up",
            acceptance_criteria=[],
            constraints=[],
            workflow="micro",
            risk="low",
            complexity="low",
            uncertainty="low",
            cost_policy="economy",
        )
        tasks.delegate_current_stage(db, project, worker_id="dirty-overlap-impl")
        (root / "app.py").write_text("VALUE = 42\n", encoding="utf-8")
        result = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Follow-up on existing WIP.",
            checks=["focused check"],
        )
        assert result["workflow_profile"] == "standard"
        assert result["active_stage"]["kind"] == "review"
        implement = [stage for stage in result["stages"] if stage["kind"] == "implement"][0]
        assert implement["changes"]["modified"] == ["app.py"]
        assert implement["changes"]["line_delta"]["status"] == "unavailable"
        assert implement["changes"]["line_delta"]["overlap"] == ["app.py"]
    finally:
        db.close()


def test_verified_terminal_dirty_state_is_allowed_as_next_task_baseline(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        _init_git_repo(root)
        first = tasks.create_task(
            db, project, goal="First managed change", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="terminal-impl")
        (root / "app.py").write_text("VALUE = 17\n", encoding="utf-8")
        review1 = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Changed value.",
            checks=["focused test"],
        )
        tasks.delegate_current_stage(db, project, worker_id="terminal-review-1")
        completed = tasks.complete_current_stage(
            db,
            project,
            expected_kind="review",
            summary="Clean review.",
            checks=["inspection"],
            verdict="pass",
        )
        assert completed["status"] == "completed"
        assert tasks._git_changed_paths(root)["paths"] == ["app.py"]

        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "create_task"
        assert nav["known_preexisting_state"]["task"] == first["key"]
        second = tasks.create_task(
            db, project, goal="Second managed change", acceptance_criteria=[], constraints=[]
        )
        assert second["key"] == "T-0002"
    finally:
        db.close()


def test_external_action_boundary_is_recorded_and_review_mutation_is_rejected(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(
            db, project, goal="External boundary", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="external-impl")
        (root / "app.py").write_text("VALUE = 22\n", encoding="utf-8")
        review = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Updated code and deployment-side cron as required.",
            checks=["focused test"],
            external_actions=[
                {
                    "kind": "mutation",
                    "target": "staging:cron/iiko-sync",
                    "summary": "Updated schedule from 10m to 5m.",
                    "evidence": "cron listing inspected after change; API_TOKEN=super-secret-token",
                }
            ],
        )
        implementation = next(item for item in review["stages"] if item["kind"] == "implement")
        assert implementation["external_actions"][0]["kind"] == "mutation"
        assert implementation["external_actions"][0]["target"] == "staging:cron/iiko-sync"
        assert "super-secret-token" not in implementation["external_actions"][0]["evidence"]
        assert "<redacted>" in implementation["external_actions"][0]["evidence"]

        tasks.delegate_current_stage(db, project, worker_id="external-review")
        with pytest.raises(ValueError, match="Read-only review cannot"):
            tasks.complete_current_stage(
                db,
                project,
                expected_kind="review",
                summary="Reviewer tried to mutate staging.",
                checks=["inspection"],
                verdict="pass",
                external_actions=[
                    {
                        "kind": "mutation",
                        "target": "staging:service",
                        "summary": "Restarted service.",
                    }
                ],
            )
        runtime = tasks.current_task(db, project, include_history=False)
        assert runtime["task"]["active_stage"]["worker_id"] == "external-review"
    finally:
        db.close()


def test_stage_specific_completion_kind_mismatch_points_to_current_stage(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(
            db, project, goal="Wrong completion surface", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="impl-kind")
        with pytest.raises(RuntimeError, match="STAGE_KIND_MISMATCH") as exc:
            tasks.complete_current_stage(
                db,
                project,
                expected_kind="review",
                summary="wrong",
                checks=["inspection"],
                verdict="pass",
            )
        assert "task_implementation_complete" in str(exc.value)
    finally:
        db.close()


def test_blocked_implementation_rejects_repository_changes_before_resume(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(
            db, project, goal="Blocked implementation guard", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="blocked-impl")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        blocked = tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Dependency unavailable.",
            checks=[],
            outcome="blocked",
        )
        assert blocked["status"] == "blocked"

        (root / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "unmanaged_stage_mutation"
        assert nav["next_action"]["code"] == "UNMANAGED_STAGE_MUTATION"
        assert nav["task"]["blocked_repository_drift"]["stage"] == "implement"
        with pytest.raises(RuntimeError, match="UNMANAGED_STAGE_MUTATION"):
            tasks.resume_task(db, project)
    finally:
        db.close()


def test_blocked_review_rejects_repository_changes_before_resume(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Blocked review guard", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="blocked-review")
        blocked = tasks.complete_stage(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="blocked-review",
            summary="Required verifier unavailable.",
            checks=[],
            outcome="blocked",
        )
        assert blocked["status"] == "blocked"

        (root / "review-side-edit.py").write_text("x = 1\n", encoding="utf-8")
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["code"] == "UNMANAGED_STAGE_MUTATION"
        assert nav["task"]["blocked_repository_drift"]["stage"] == "review"
        with pytest.raises(RuntimeError, match="UNMANAGED_STAGE_MUTATION"):
            tasks.resume_task(db, project)
    finally:
        db.close()


def test_blocked_fix_rejects_repository_changes_before_resume(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Blocked fix guard", acceptance_criteria=[], constraints=[]
        )
        review = _complete_implement(db, project, created, root)
        fix = _complete_bound(
            db,
            project,
            stage_id=review["active_stage"]["id"],
            worker_id="reviewer-for-blocked-fix",
            summary="Found one issue.",
            checks=["inspection"],
            verdict="changes_required",
            findings=[
                {
                    "severity": "medium",
                    "category": "correctness",
                    "path": "app.py",
                    "problem": "Needs another value.",
                    "required_fix": "Adjust value.",
                }
            ],
        )
        tasks.delegate_current_stage(db, project, worker_id="blocked-fixer")
        (root / "app.py").write_text("VALUE = 4\n", encoding="utf-8")
        blocked = tasks.complete_current_stage(
            db,
            project,
            expected_kind="fix",
            summary="Cannot finish until local dependency is restored.",
            checks=[],
            outcome="blocked",
        )
        assert blocked["status"] == "blocked"

        (root / "app.py").write_text("VALUE = 5\n", encoding="utf-8")
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["code"] == "UNMANAGED_STAGE_MUTATION"
        assert nav["task"]["blocked_repository_drift"]["stage"] == "fix"
        with pytest.raises(RuntimeError, match="UNMANAGED_STAGE_MUTATION"):
            tasks.resume_task(db, project)
    finally:
        db.close()


def test_blocked_stage_can_resume_when_repository_still_matches_blocked_digest(tmp_path: Path):
    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(
            db, project, goal="Clean blocked resume", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="blocked-clean")
        (root / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        tasks.complete_current_stage(
            db,
            project,
            expected_kind="implement",
            summary="Waiting on dependency.",
            checks=[],
            outcome="blocked",
        )
        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "resolve_blocker_then_resume"
        resumed = tasks.resume_task(db, project)
        assert resumed["status"] == "active"
        assert resumed["active_stage"]["kind"] == "implement"
        assert resumed["active_stage"]["worker_id"] is None
    finally:
        db.close()


def test_legacy_active_stage_has_one_time_completion_route_without_retroactive_delegation(
    tmp_path: Path,
):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Legacy in-flight stage", acceptance_criteria=[], constraints=[]
        )
        stage = db.get(TaskStage, UUID(created["active_stage"]["id"]))
        stage.delegation_required = False
        db.commit()
        (root / "app.py").write_text("VALUE = 77\n", encoding="utf-8")

        nav = tasks.next_task_action(db, project)
        assert nav["next_action"]["action"] == "record_legacy_stage_result"
        assert nav["next_action"]["tool"] == "task_stage_complete"
        assert nav["next_action"]["stage_id"] == str(stage.id)
        assert nav["task"]["legacy_stage_compatibility"]["delegation_required"] is False
        assert nav["task"]["active_stage"]["delegated"] is False
        assert nav["task"]["active_stage"]["explicitly_delegated"] is False
        assert (
            nav["task"]["active_stage"]["delegation_assurance"] == "legacy-no-explicit-delegation"
        )
        with pytest.raises(RuntimeError, match="LEGACY_STAGE_NO_RETROACTIVE_DELEGATION"):
            tasks.delegate_current_stage(db, project, worker_id="retroactive-worker")

        next_state = tasks.complete_stage(
            db,
            project,
            stage_id=str(stage.id),
            worker_id="legacy-worker-label",
            summary="Completed work that was already in flight before delegation enforcement.",
            checks=["legacy focused verification passed"],
        )
        assert next_state["active_stage"]["kind"] == "review"
        assert next_state["active_stage"]["delegation_required"] is True
        assert next_state["active_stage"]["worker_id"] is None
        assert tasks.next_task_action(db, project)["next_action"]["tool"] == "task_stage_delegate"
    finally:
        db.close()


def test_dashboard_state_uses_authoritative_task_next_navigation(tmp_path: Path, monkeypatch):
    from contextlib import contextmanager
    from ai_layer.application import tasks as application_tasks

    db, project, root = _db_project(tmp_path)
    try:
        tasks.create_task(
            db, project, goal="Dashboard authoritative nav", acceptance_criteria=[], constraints=[]
        )
        (root / "app.py").write_text("VALUE = 99\n", encoding="utf-8")

        @contextmanager
        def fake_scope():
            yield db

        monkeypatch.setattr(application_tasks, "session_scope", fake_scope)
        dashboard = read_task_state(root)
        assert dashboard["source"] == "database"
        assert dashboard["next_action"]["action"] == "unmanaged_stage_mutation"
        assert dashboard["next_action"]["code"] == "UNMANAGED_STAGE_MUTATION"
        assert dashboard["current"]["next_action"] == dashboard["next_action"]
    finally:
        db.close()


def test_dashboard_state_exposes_create_task_navigation_when_only_historical_task_remains(
    tmp_path: Path, monkeypatch
):
    from contextlib import contextmanager
    from ai_layer.application import tasks as application_tasks

    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Historical dashboard nav", acceptance_criteria=[], constraints=[]
        )
        tasks.cancel_task(db, project, reason="fixture complete")

        @contextmanager
        def fake_scope():
            yield db

        monkeypatch.setattr(application_tasks, "session_scope", fake_scope)
        dashboard = read_task_state(root)
        assert dashboard["current"] is None
        assert dashboard["latest"]["id"] == created["id"]
        assert dashboard["latest"]["next_action"]["action"] == "none"
        assert dashboard["next_action"]["action"] == "create_task"
        assert dashboard["next_action"]["tool"] == "task_create"
    finally:
        db.close()


def test_delegation_contract_requires_adaptive_expertise_and_documentation_impact_review(
    tmp_path: Path,
):
    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db,
            project,
            goal="Change deployment config",
            acceptance_criteria=["safe"],
            constraints=[],
        )
        contract = created["delegation_contract"]
        assert contract["expertise_contract"]["routing_owner"].startswith("The host agent")
        assert "skill_get" in contract["expertise_contract"]["authoritative_content"]
        assert "required/recommended/on-demand" in contract["expertise_contract"]["routing_owner"]
        assert any("documentation impact" in item.casefold() for item in contract["requirements"])
        review = _complete_implement(db, project, created, root)
        assert any(
            "documentation impact" in item.casefold()
            for item in review["delegation_contract"]["requirements"]
        )
    finally:
        db.close()


def test_task_contract_rejects_oversized_durable_payloads(tmp_path: Path):
    import pytest

    db, project, root = _db_project(tmp_path)
    try:
        with pytest.raises(ValueError, match="8000-character limit"):
            tasks.create_task(
                db,
                project,
                goal="x" * 8001,
                acceptance_criteria=[],
                constraints=[],
            )

        created = tasks.create_task(
            db, project, goal="Bound stage payload", acceptance_criteria=[], constraints=[]
        )
        tasks.delegate_current_stage(db, project, worker_id="bounded-implementer")
        stage_id = created["active_stage"]["id"]
        with pytest.raises(ValueError, match="50-item limit"):
            tasks.complete_stage(
                db,
                project,
                stage_id=stage_id,
                worker_id="bounded-implementer",
                summary="implemented",
                checks=["ok"],
                external_actions=[
                    {"kind": "verification", "target": f"target-{index}", "summary": "checked"}
                    for index in range(51)
                ],
            )
        with pytest.raises(ValueError, match="8000-character limit"):
            tasks.complete_stage(
                db,
                project,
                stage_id=stage_id,
                worker_id="bounded-implementer",
                summary="x" * 8001,
                checks=["ok"],
            )
        with pytest.raises(ValueError, match="64000-byte limit"):
            tasks.complete_stage(
                db,
                project,
                stage_id=stage_id,
                worker_id="bounded-implementer",
                summary="implemented",
                checks=["ok"],
                result_data={"payload": "x" * 65000},
            )
    finally:
        db.close()


def test_review_check_rejects_unbounded_command_payload(tmp_path: Path):
    import pytest

    db, project, root = _db_project(tmp_path)
    try:
        created = tasks.create_task(
            db, project, goal="Bound review command", acceptance_criteria=[], constraints=[]
        )
        _complete_implement(db, project, created, root)
        tasks.delegate_current_stage(db, project, worker_id="bounded-reviewer")
        with pytest.raises(ValueError, match="64-argument limit"):
            tasks.run_current_review_check(
                db,
                project,
                command=["python", *[f"arg-{index}" for index in range(64)]],
            )
        with pytest.raises(ValueError, match="8000-character limit"):
            tasks.run_current_review_check(
                db,
                project,
                command=["python", "x" * 8001],
            )
    finally:
        db.close()
