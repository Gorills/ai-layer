from __future__ import annotations

from pathlib import Path

from ai_layer.db.models import Project, Task
from ai_layer.tasks.constants import MICRO_MAX_CHANGED_LINES, SENSITIVE_PATH_TERMS
from ai_layer.workspace.repository import git_changed_line_count


def micro_envelope(project: Project, task: Task, changes: dict, external_actions: list[dict]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if (task.risk_level or "normal") != "low":
        reasons.append("risk is not low")
    if bool(changes.get("truncated")):
        reasons.append("diff path list is truncated")
    total = int(changes.get("total") or 0)
    if total == 0:
        reasons.append("micro implementation produced no managed repository changes")
    if total > 2:
        reasons.append(f"changed paths {total} exceed micro limit 2")
    paths = [*(changes.get("added") or []), *(changes.get("modified") or []), *(changes.get("deleted") or [])]
    sensitive = [p for p in paths if any(term in str(p).casefold() for term in SENSITIVE_PATH_TERMS)]
    if sensitive:
        reasons.append("sensitive path touched: " + ", ".join(sensitive[:4]))
    added_code = [
        p for p in (changes.get("added") or [])
        if Path(str(p)).suffix.lower() not in {".md", ".txt"} and "test" not in str(p).casefold()
    ]
    if added_code:
        reasons.append("new non-test code file added")
    preexisting = dict(task.preexisting_changes or {})
    preexisting_paths = set(str(p) for p in (preexisting.get("paths") or []))
    overlap = sorted(preexisting_paths.intersection(str(p) for p in paths))
    if bool(preexisting.get("truncated")):
        line_stats = None
        changes["line_delta"] = {
            "status": "unavailable",
            "reason": "pre-existing dirty path inventory was truncated at task baseline",
        }
        reasons.append(
            "micro task started from a large truncated dirty baseline; exact overlap cannot be proven"
        )
    elif overlap:
        line_stats = None
        changes["line_delta"] = {
            "status": "unavailable",
            "reason": "task modified path(s) that were already dirty at baseline",
            "overlap": overlap[:8],
        }
        reasons.append(
            "micro task overlaps pre-existing dirty baseline; exact line delta relative to task baseline is unavailable"
        )
    else:
        line_stats = git_changed_line_count(Path(project.root_path).expanduser().resolve(), changes)
        changes["line_delta"] = line_stats or {"status": "unavailable"}
        if line_stats is None:
            reasons.append("changed-line count unavailable")
        elif bool(line_stats.get("binary")):
            reasons.append("binary diff is not eligible for micro completion")
        elif int(line_stats.get("total") or 0) > MICRO_MAX_CHANGED_LINES:
            reasons.append(f"changed lines {int(line_stats.get('total') or 0)} exceed micro limit {MICRO_MAX_CHANGED_LINES}")
    if any(item.get("kind") == "mutation" for item in external_actions):
        reasons.append("external mutation was required")
    return not reasons, reasons
