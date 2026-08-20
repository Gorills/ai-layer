from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise AssertionError(f"{path}: expected one match, got {count}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


project_path = "src/ai_layer/dashboard/static/js/views/project.js"
replace_once(
    project_path,
    'import { workAttentionReason, workDisplayState, workHref } from "./work.js";',
    'import { workAttentionReason, workCompletionAction, workDisplayState, workHref } from "./work.js";',
)
replace_once(
    project_path,
    '  for (const work of (project.work?.attention || []).slice(0, 4)) {',
    '  for (const work of project.work?.attention || []) {',
)
replace_once(
    project_path,
    '<div class="panel-header"><div><div class="panel-title">Сейчас</div><div class="panel-hint">Один текущий контекст вместо разрозненных экранов</div></div>${work ? stateBadge(workDisplayState(work)) : stateBadge(task?.status || "idle")}</div>',
    '<div class="panel-header"><div><div class="panel-title">Сейчас</div><div class="panel-hint">Приоритетный текущий контекст; все open WorkItems показаны ниже</div></div>${work ? stateBadge(workDisplayState(work)) : stateBadge(task?.status || "idle")}</div>',
)
open_panel = '''function openWorkPanel(data) {
  const project = data.project || {};
  const items = project.work?.active || [];
  const liveCount = items.filter((item) => item.live).length;
  return `<section class="panel open-work-panel">
    <div class="panel-header"><div><div class="panel-title">Открытые WorkItems</div><div class="panel-hint">Все незавершённые Work проекта. Live Work нельзя закрыть одним кликом.</div></div><span class="muted">${escapeHtml(items.length)}</span></div>
    ${items.length ? `<div class="workspace-record-list">${items.map((work) => `<div class="workspace-record">
      <a class="workspace-record-main" href="${workHref(project.key, work.key)}">
        <div class="record-kicker">${escapeHtml(work.key || "Work")} · ${escapeHtml(work.kind || "work")}</div>
        <div class="record-title">${escapeHtml(work.goal || "—")}</div>
        <div class="record-meta">${escapeHtml(work.live ? "live" : workAttentionReason(work))} · ${escapeHtml(work.updated_at ? age(work.updated_at) : "")}</div>
      </a>
      <div class="toolbar-controls">${stateBadge(workDisplayState(work))}${workCompletionAction(project, work)}</div>
    </div>`).join("")}</div>` : `<div class="calm-state"><strong>Open Work нет</strong><span>Все WorkItems проекта завершены или ещё не создавались.</span></div>`}
    ${items.length ? `<div class="panel-footer"><span class="muted">${escapeHtml(liveCount)} live · ${escapeHtml(items.length - liveCount)} non-live</span><a class="panel-header-link" href="#/project/${encodeURIComponent(project.key)}/work">Вся работа →</a></div>` : ""}
  </section>`;
}

'''
replace_once(project_path, "function recentResults(data) {", open_panel + "function recentResults(data) {")
replace_once(
    project_path,
    '''  const work = project.work || {};
  const recent = recentWork(project);
  const active = currentWork(project);
  const attention = attentionItems(data);''',
    '''  const work = project.work || {};
  const open = work.active || [];
  const liveCount = open.filter((item) => item.live).length;
  const recent = recentWork(project);
  const attention = attentionItems(data);''',
)
replace_once(
    project_path,
    '${metric("Сейчас", active ? active.key : "пауза", active?.goal || "активной работы нет")}',
    '${metric("Открытые Work", open.length, open.length ? `${liveCount} live · ${open.length - liveCount} non-live` : "активной работы нет")}',
)
replace_once(
    project_path,
    '''        ${nowPanel(data)}
        ${recentResults(data)}''',
    '''        ${nowPanel(data)}
        ${openWorkPanel(data)}
        ${recentResults(data)}''',
)

overview_path = "src/ai_layer/dashboard/static/js/views/overview.js"
replace_once(
    overview_path,
    'import { collectPortfolioWork, primaryProjectWork, workAttentionReason, workHref } from "./work.js";',
    'import { collectPortfolioWork, primaryProjectWork, workAttentionReason, workCompletionAction, workHref } from "./work.js";',
)
replace_once(
    overview_path,
    '''      state: work.status === "active" && !work.live ? "stale" : work.status || "attention",
      href: workHref(project.key, work.key),''',
    '''      state: work.status === "active" && !work.live ? "stale" : work.status || "attention",
      href: workHref(project.key, work.key),
      work,''',
)
old_attention_list = '''function attentionList(items) {
  if (!items?.length) return `<div class="calm-state large"><strong>Ничего не требует вмешательства</strong><span>Нет blocked/stale работы, решений пользователя, protocol warnings или stale Project Map.</span></div>`;
  return `<div class="attention-work-list">${items.map((item) => `<a class="attention-work-row" href="${item.href}">
    <div class="attention-work-project">${escapeHtml(item.project.name)}</div>
    <div class="attention-work-main"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></div>
    ${stateBadge(item.state)}
  </a>`).join("")}</div>`;
}'''
new_attention_list = '''function attentionList(items) {
  if (!items?.length) return `<div class="calm-state large"><strong>Ничего не требует вмешательства</strong><span>Нет blocked/stale работы, решений пользователя, protocol warnings или stale Project Map.</span></div>`;
  return `<div class="attention-work-list">${items.map((item) => `<div class="attention-work-row">
    <a class="attention-work-project" href="${item.href}">${escapeHtml(item.project.name)}</a>
    <a class="attention-work-main" href="${item.href}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></a>
    <div class="toolbar-controls">${stateBadge(item.state)}${item.work ? workCompletionAction(item.project, item.work) : ""}</div>
  </div>`).join("")}</div>`;
}'''
replace_once(overview_path, old_attention_list, new_attention_list)

test_path = Path("tests/test_dashboard_open_work_overview.py")
if test_path.exists():
    raise AssertionError(f"{test_path} already exists")
test_path.write_text(
    '''from __future__ import annotations

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
        "\\n".join(
            [
                f"import {{ renderProject }} from '{project_url}';",
                "const live = { key: 'W-0001', goal: 'Live work', kind: 'change', status: 'active', live: true, runs: [], updated_at: '2026-08-20T00:00:00Z' };",
                "const waiting = { key: 'W-0002', goal: 'Waiting work', kind: 'change', status: 'awaiting_feedback', live: false, runs: [], updated_at: '2026-08-20T00:00:00Z' };",
                "const blocked = { key: 'W-0003', goal: 'Blocked work', kind: 'change', status: 'blocked', live: false, runs: [], updated_at: '2026-08-20T00:00:00Z' };",
                "const html = renderProject({ project: { key: 'alpha/beta', name: 'Alpha', root: '/tmp/alpha', task: {}, protocol_state: {}, project_map: {}, agents: [], work: { active: [live, waiting, blocked], live: [live], attention: [waiting, blocked], recent: [] } }, metrics: {} });",
                "for (const key of ['W-0001', 'W-0002', 'W-0003']) if (!html.includes(key)) throw new Error(`missing ${key}`);",
                "if (!html.includes('Открытые WorkItems')) throw new Error('missing open Work panel');",
                "if (!html.includes('1 live · 2 non-live')) throw new Error('missing open Work totals');",
                "const forms = html.match(/<form method=\\\"post\\\"/g) || [];",
                "if (forms.length !== 2) throw new Error(`expected 2 completion forms, got ${forms.length}`);",
                "if (!html.includes('work_key=W-0002') || !html.includes('work_key=W-0003')) throw new Error('non-live actions missing');",
                "if (html.includes('work_key=W-0001')) throw new Error('live completion action leaked');",
            ]
        )
        + "\\n",
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

    assert ".slice(0, 4)" not in project_source
    assert "${openWorkPanel(data)}" in project_source
    assert 'metric("Открытые Work", open.length' in project_source
    assert "workCompletionAction(project, work)" in project_source
    assert "workCompletionAction(item.project, item.work)" in overview_source
    assert '<div class="attention-work-row">' in overview_source
''',
    encoding="utf-8",
)
