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
    "src/ai_layer/dashboard/static/js/app.js",
    '''function scopedHref(root, projectKey) {
  if (root === "overview") return "#/overview";
  if (root === "project") return projectKey ? `#/project/${encodeURIComponent(projectKey)}` : "#/overview";
  if (FILTERABLE_ROOTS.has(root)) return hashUrl(root, { project: projectKey || null });
  return `#/${root}`;
}
''',
    '''function scopedHref(root, projectKey) {
  if (root === "overview") return "#/overview";
  if (root === "project") return projectKey ? `#/project/${encodeURIComponent(projectKey)}` : "#/overview";
  if (projectKey && root === "work") return `#/project/${encodeURIComponent(projectKey)}/work`;
  if (projectKey && root === "knowledge") return `#/project/${encodeURIComponent(projectKey)}/knowledge`;
  if (FILTERABLE_ROOTS.has(root)) return hashUrl(root, { project: projectKey || null });
  return `#/${root}`;
}
''',
)

replace(
    "src/ai_layer/dashboard/static/js/app.js",
    '''    <div class="project-choice-grid">${projects.map((project) => `<a class="project-choice" href="#/project/${encodeURIComponent(project.key)}"><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.root || "")}</span></a>`).join("") || `<div class="empty">Зарегистрированных проектов нет</div>`}</div>
''',
    '''    <div class="project-choice-grid">${projects.map((project) => `<a class="project-choice" href="#/project/${encodeURIComponent(project.key)}/knowledge"><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.root || "")}</span></a>`).join("") || `<div class="empty">Зарегистрированных проектов нет</div>`}</div>
''',
)

replace(
    "tests/test_dashboard_project_workspace_ux.py",
    '''    assert "function scopedHref" in app_js
    assert "element.href = scopedHref(target, knownProject)" in app_js
''',
    '''    assert "function scopedHref" in app_js
    assert 'projectKey && root === "work"' in app_js
    assert 'projectKey && root === "knowledge"' in app_js
    assert "element.href = scopedHref(target, knownProject)" in app_js
''',
)

replace(
    "tests/test_dashboard_project_workspace_ux.py",
    '''    assert "Project Knowledge всегда принадлежит конкретному проекту" in app_js
    assert "overviewCache.projects?.[0]?.key" not in app_js
''',
    '''    assert "Project Knowledge всегда принадлежит конкретному проекту" in app_js
    assert 'href="#/project/${encodeURIComponent(project.key)}/knowledge"' in app_js
    assert "overviewCache.projects?.[0]?.key" not in app_js
''',
)
