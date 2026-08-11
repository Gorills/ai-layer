from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_layer.db.models import RepositorySnapshot, Task, TaskStage


def accepted_task_identity(db: Session, task: Task) -> dict[str, object]:
    """Return the repository identity actually observed by the Task's terminal read-only stage.

    Epics must never bless whatever happens to be in the worktree when the scheduler later notices
    that a Task completed. STANDARD Epic Tasks terminate in REVIEW and reconciliation Tasks terminate
    in DISCOVERY; both are read-only, so their durable stage evidence is the accepted boundary.
    """
    stage = db.scalar(
        select(TaskStage)
        .where(TaskStage.task_id == task.id, TaskStage.status == "completed")
        .order_by(TaskStage.ordinal.desc())
        .limit(1)
    )
    if stage is None:
        return {"digest": str(task.baseline_digest or ""), "file_count": int(task.baseline_files or 0)}

    digest = str(stage.repository_digest_after or stage.repository_digest_before or "")
    file_count = int(task.baseline_files or 0)
    if stage.start_snapshot_id is not None:
        snapshot = db.get(RepositorySnapshot, stage.start_snapshot_id)
        if snapshot is not None:
            file_count = int(snapshot.file_count)
            if not digest:
                digest = str(snapshot.digest or "")

    if not digest:
        digest = str(task.baseline_digest or "")
    return {"digest": digest, "file_count": file_count}
