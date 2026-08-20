from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "src/ai_layer/dashboard/static/js/views/project.js"
TEST = ROOT / "tests/test_dashboard_project_cockpit.py"


def replace_exact(text: str, old: str, new: str, *, count: int, label: str) -> str:
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{label}: expected {count} matches, got {actual}")
    return text.replace(old, new)


project = PROJECT.read_text(encoding="utf-8")
imports = (
    'import { workAttentionReason, workCompletionAction, workDisplayState, workHref } from "./work.js";\n\n'
)
open_epic_statuses = (
    'const OPEN_EPIC_STATUSES = new Set(["draft", "approved", "phase0", "planning", "running", "final_review", "blocked"]);\n\n'
)
if open_epic_statuses not in project:
    project = replace_exact(
        project,
        imports,
        imports + open_epic_statuses,
        count=1,
        label="open Epic status contract insertion",
    )
project = replace_exact(
    project,
    'const activeEpics = allEpics.filter((item) => !["completed", "cancelled", "failed", "abandoned"].includes(item.status));',
    "const activeEpics = allEpics.filter((item) => OPEN_EPIC_STATUSES.has(item.status));",
    count=2,
    label="active Epic filters",
)
PROJECT.write_text(project, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
marker = '    assert "${workflowPanel(data)}" in source\n'
regression = (
    '    assert "OPEN_EPIC_STATUSES = new Set" in source\n'
    '    assert source.count("OPEN_EPIC_STATUSES.has(item.status)") == 2\n'
)
if regression not in test:
    test = replace_exact(
        test,
        marker,
        marker + regression,
        count=1,
        label="Epic status regression assertions",
    )
TEST.write_text(test, encoding="utf-8")
subprocess.run([sys.executable, "-m", "ruff", "format", str(TEST)], check=True)
