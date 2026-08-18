from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{path}: expected {count} match(es), found {found}: {old[:120]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


replace(
    "tests/test_dashboard.py",
    '    assert "Текущее состояние локального AI workspace" in page.text\n',
    '    assert "Рабочий проект" in page.text\n    assert "Сводка проекта" in page.text\n',
)

replace(
    "tests/test_dashboard_redesign.py",
    '    assert "slice(0, 10)" in project_js\n',
    '    assert "slice(0, 5)" in project_js\n',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''function recentWork(project) {
  return (project?.work?.recent || []).slice(0, 5);
}
''',
    '''function recentWork(project) {
  return (project?.work?.recent || []).slice(0, 5);
}

function mapFreshness(map) {
  if (map?.error) return "error";
  if (Number(map?.semantic_stale || 0) > 0 || Number(map?.semantic_missing || 0) > 0) return "stale";
  if (Number(map?.semantic_entries || 0) > 0 || Number(map?.semantic_current || 0) > 0) return "current";
  return "unknown";
}
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''  const work = currentWork(project);
  const task = project.task;
''',
    '''  const work = currentWork(project);
  const task = ["active", "blocked"].includes(project.task?.status) ? project.task : null;
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '  const freshness = project.intelligence?.freshness || {};\n',
    '  const freshness = mapFreshness(project.project_map || {});\n',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''  if (["stale", "missing"].includes(String(freshness.status || "").toLowerCase())) {
    items.push({ title: "Project Intelligence требует обновления", reason: freshness.status, href: `#/project/${encodeURIComponent(project.key)}/knowledge` });
  }
''',
    '''  if (["stale", "error"].includes(freshness)) {
    items.push({ title: "Project Map требует обновления", reason: freshness, href: `#/project/${encodeURIComponent(project.key)}/knowledge` });
  }
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''  const intelligence = project.intelligence || {};
  const map = intelligence.project_map || project.project_map || {};
  const freshness = intelligence.freshness || {};
  const focus = intelligence.current_focus || null;
''',
    '''  const map = project.project_map || {};
  const freshness = mapFreshness(map);
  const focusWork = currentWork(project);
  const focusTask = ["active", "blocked"].includes(project.task?.status) ? project.task : null;
  const focus = focusWork
    ? { kind: "Work", key: focusWork.key, title: focusWork.goal }
    : focusTask
      ? { kind: "Task", key: focusTask.key, title: focusTask.goal }
      : null;
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''      ${infoRow("Project Map", map.navigation_files != null ? `${map.navigation_files} файлов · ${map.symbol_count ?? 0} symbols` : "—", freshness.status || "unknown")}
''',
    '''      ${infoRow("Project Map", `${map.semantic_current ?? 0} current · ${map.semantic_stale ?? 0} stale`, freshness)}
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''  const intelligence = project.intelligence || {};
  const map = intelligence.project_map || project.project_map || {};
  const freshness = intelligence.freshness || {};
''',
    '''  const map = project.project_map || {};
  const freshness = mapFreshness(map);
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''      ${metric("Project Map", map.navigation_files != null ? `${map.navigation_files} файлов` : "—", `${escapeHtml(map.symbol_count ?? 0)} symbols · ${escapeHtml(freshness.status || "unknown")}`)}
''',
    '''      ${metric("Project Map", `${escapeHtml(map.semantic_current ?? 0)} current`, `${escapeHtml(map.semantic_stale ?? 0)} stale · ${escapeHtml(map.semantic_missing ?? 0)} missing`)}
''',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '${stateBadge(String(freshness.status || "unknown").toLowerCase())}',
    '${stateBadge(freshness)}',
)

replace(
    "src/ai_layer/dashboard/static/js/views/project.js",
    '''            ${infoRow("Navigation files", map.navigation_files ?? "—")}
            ${infoRow("Symbols", map.symbol_count ?? "—")}
            ${infoRow("Freshness", freshness.status || "unknown")}
            ${infoRow("Execution owner", intelligence.execution_owner || "host-native")}
''',
    '''            ${infoRow("Semantic entries", map.semantic_entries ?? "—")}
            ${infoRow("Current", map.semantic_current ?? "—")}
            ${infoRow("Stale / missing", `${map.semantic_stale ?? 0} / ${map.semantic_missing ?? 0}`)}
            ${infoRow("Freshness", freshness)}
            ${infoRow("Execution owner", "host-native")}
''',
)

replace(
    "tests/test_dashboard_project_workspace_ux.py",
    '''    assert "workMethod(work)" in project_js
    assert "Promise.all([" in app_js
''',
    '''    assert "workMethod(work)" in project_js
    assert '["active", "blocked"].includes(project.task?.status)' in project_js
    assert "project.intelligence" not in project_js
    assert "navigation_files" not in project_js
    assert "semantic_current" in project_js
    assert "Promise.all([" in app_js
''',
)
