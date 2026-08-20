from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_JS = ROOT / "src/ai_layer/dashboard/static/js/views/project.js"
OVERVIEW_JS = ROOT / "src/ai_layer/dashboard/static/js/views/overview.js"


def test_project_overview_keeps_every_open_work_visible_and_actionable(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        raise AssertionError("node is required to execute Dashboard project view helpers")

    script = tmp_path / "project_open_work_check.mjs"
    project_url = PROJECT_JS.resolve().as_uri()
    script.write_text(
        "\n".join(
            [
                f"import {{ renderProject }} from '{project_url}';",
                "const live = { key: 'W-0001', goal: 'Live work', kind: 'change', status: 'active', live: true, runs: [], updated_at: '2026-08-20T00:00:00Z' };",
                "const waiting = { key: 'W-0002', goal: 'Waiting work', kind: 'change', status: 'awaiting_feedback', live: false, runs: [], updated_at: '2026-08-20T00:00:00Z' };",
                "const blocked = { key: 'W-0003', goal: 'Blocked work', kind: 'change', status: 'blocked', live: false, runs: [], updated_at: '2026-08-20T00:00:00Z' };",
                "const html = renderProject({ project: { key: 'alpha/beta', name: 'Alpha', root: '/tmp/alpha', task: {}, protocol_state: {}, project_map: {}, agents: [], work: { active: [live, waiting, blocked], live: [live], attention: [waiting, blocked], recent: [] } }, metrics: {} });",
                "for (const key of ['W-0001', 'W-0002', 'W-0003']) if (!html.includes(key)) throw new Error(`missing ${key}`);",
                "if (!html.includes('Открытые WorkItems')) throw new Error('missing open Work panel');",
                "if (!html.includes('1 live · 2 non-live')) throw new Error('missing open Work totals');",
                'const forms = html.match(/<form method="post"/g) || [];',
                "if (forms.length !== 2) throw new Error(`expected 2 completion forms, got ${forms.length}`);",
                "if (!html.includes('work_key=W-0002') || !html.includes('work_key=W-0003')) throw new Error('non-live actions missing');",
                "if (html.includes('work_key=W-0001')) throw new Error('live completion action leaked');",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", script],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_overviews_do_not_hide_open_work_or_require_detail_for_completion() -> None:
    project_source = PROJECT_JS.read_text(encoding="utf-8")
    overview_source = OVERVIEW_JS.read_text(encoding="utf-8")

    assert "project.work?.attention || []).slice(0, 4)" not in project_source
    assert "${openWorkPanel(data)}" in project_source
    assert 'metric("Открытые Work", open.length' in project_source
    assert "workCompletionAction(project, work)" in project_source
    assert "workCompletionAction(item.project, item.work)" in overview_source
    assert '<div class="attention-work-row">' in overview_source
    assert '<a class="attention-work-row"' not in overview_source
