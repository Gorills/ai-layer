from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/ai_layer/dashboard/static/js/app.js"
PROJECT = ROOT / "src/ai_layer/dashboard/static/js/views/project.js"
CSS = ROOT / "src/ai_layer/dashboard/static/css/workspace.css"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return updated


app = APP.read_text(encoding="utf-8")
app = replace_once(
    app,
    "let lastScopeFingerprint = null;\n",
    """let lastScopeFingerprint = null;

const PROJECT_COCKPIT_CACHE_MS = IDLE_POLL_MS;
const projectCockpitCache = new Map();

async function projectCockpitData(projectKey) {
  const cached = projectCockpitCache.get(projectKey);
  if (cached && Date.now() - cached.cachedAt < PROJECT_COCKPIT_CACHE_MS) return cached.data;
  const [tasks, epics] = await Promise.all([
    api.tasks({ project_key: projectKey, page: 1, page_size: 6 }),
    api.epics({ project_key: projectKey, page: 1, page_size: 6 }),
  ]);
  const data = { tasks, epics };
  projectCockpitCache.set(projectKey, { cachedAt: Date.now(), data });
  return data;
}
""",
    "cockpit cache",
)
app = replace_once(
    app,
    """    } else if (current.kind === "project") {
      const data = await api.project(current.key);
      renderChanged(current, data, () => {
        setPage(data.project?.name || "Проект", "Что происходит сейчас, что было сделано и что важно знать");
        app.innerHTML = renderProject(data);
      });
      generatedAt = data.generated_at;
      nextPollMs = projectIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
""",
    """    } else if (current.kind === "project") {
      const [projectData, cockpit] = await Promise.all([
        api.project(current.key),
        projectCockpitData(current.key),
      ]);
      const data = { ...projectData, tasks: cockpit.tasks, epics: cockpit.epics };
      renderChanged(current, data, () => {
        setPage(data.project?.name || "Проект", "Cockpit: текущая работа, решения, Tasks, Epics и последние результаты");
        app.innerHTML = renderProject(data);
      });
      generatedAt = projectData.generated_at;
      nextPollMs = projectIsLive(projectData) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
""",
    "project route",
)
app = replace_once(
    app,
    """  if (resetOverview) {
    overviewCache = null;
    overviewCachedAt = 0;
  }
""",
    """  if (resetOverview) {
    overviewCache = null;
    overviewCachedAt = 0;
    projectCockpitCache.clear();
  }
""",
    "manual refresh cache reset",
)
APP.write_text(app, encoding="utf-8")

project = PROJECT.read_text(encoding="utf-8")
project = regex_once(
    project,
    r"\nfunction nowPanel\(data\) \{.*?\n\}\n\nfunction openWorkPanel",
    "\nfunction openWorkPanel",
    "remove duplicate now panel",
)

open_panel = r"""function openWorkPanel(data) {
  const project = data.project || {};
  const items = project.work?.active || [];
  const focus = currentWork(project);
  const liveCount = items.filter((item) => item.live).length;
  return `<section class="panel open-work-panel">
    <div class="panel-header"><div><div class="panel-title">В работе</div><div class="panel-hint">Все незавершённые Work проекта; текущий фокус выделен, live Work защищён от механического закрытия.</div></div><span class="muted">${escapeHtml(items.length)}</span></div>
    ${items.length ? `<div class="workspace-record-list">${items.map((work) => {
      const focused = focus?.key === work.key;
      return `<div class="workspace-record cockpit-work-row ${focused ? "is-focus" : ""}">
        <a class="workspace-record-main" href="${workHref(project.key, work.key)}">
          <div class="record-kicker">${focused ? '<span class="cockpit-focus-label">Текущий фокус</span>' : ""}${escapeHtml(work.key || "Work")} · ${escapeHtml(work.kind || "work")}</div>
          <div class="record-title">${escapeHtml(work.goal || "—")}</div>
          <div class="record-meta">${escapeHtml(work.live ? "live" : workAttentionReason(work))} · ${escapeHtml(work.updated_at ? age(work.updated_at) : "")}</div>
        </a>
        <div class="toolbar-controls">${stateBadge(workDisplayState(work))}${workCompletionAction(project, work)}</div>
      </div>`;
    }).join("")}</div>` : `<div class="calm-state"><strong>Open Work нет</strong><span>Все WorkItems проекта завершены или ещё не создавались.</span></div>`}
    ${items.length ? `<div class="panel-footer"><span class="muted">${escapeHtml(liveCount)} live · ${escapeHtml(items.length - liveCount)} non-live</span><a class="panel-header-link" href="#/project/${encodeURIComponent(project.key)}/work">Глубокий обзор работы →</a></div>` : ""}
  </section>`;
}

function workflowPanel(data) {
  const project = data.project || {};
  const allTasks = data.tasks?.items || [];
  const allEpics = data.epics?.items || [];
  const activeTasks = allTasks.filter((item) => ["active", "blocked"].includes(item.status));
  const activeEpics = allEpics.filter((item) => !["completed", "cancelled", "failed", "abandoned"].includes(item.status));
  const tasks = (activeTasks.length ? activeTasks : allTasks).slice(0, 3);
  const epics = (activeEpics.length ? activeEpics : allEpics).slice(0, 3);
  return `<section class="panel cockpit-workflow-panel">
    <div class="panel-header"><div><div class="panel-title">План и assurance</div><div class="panel-hint">Managed Tasks и Epics доступны прямо в cockpit; отдельный экран нужен только для деталей.</div></div></div>
    <div class="cockpit-workflow-group">
      <div class="cockpit-workflow-head"><strong>Managed Tasks</strong><a href="${hashUrl("tasks", { project: project.key })}">Все →</a></div>
      ${tasks.length ? taskList(project.key, tasks) : `<div class="cockpit-empty-line">Активных Managed Tasks нет</div>`}
    </div>
    <div class="cockpit-workflow-group">
      <div class="cockpit-workflow-head"><strong>Epics</strong><a href="${hashUrl("epics", { project: project.key })}">Все →</a></div>
      ${epics.length ? epicList(project.key, epics) : `<div class="cockpit-empty-line">Активных Epics нет</div>`}
    </div>
  </section>`;
}

function recentResults"""
project = regex_once(
    project,
    r"function openWorkPanel\(data\) \{.*?\n\}\n\nfunction recentResults",
    open_panel,
    "open work and workflow panels",
)
project = replace_once(
    project,
    '<div><div class="section-eyebrow">PROJECT WORKSPACE</div>',
    '<div><div class="section-eyebrow">PROJECT COCKPIT</div>',
    "project eyebrow",
)

render_project = r"""export function renderProject(data) {
  const project = data.project || {};
  const work = project.work || {};
  const open = work.active || [];
  const liveCount = open.filter((item) => item.live).length;
  const recent = recentWork(project);
  const attention = attentionItems(data);
  const activeTasks = (data.tasks?.items || []).filter((item) => ["active", "blocked"].includes(item.status));
  const activeEpics = (data.epics?.items || []).filter((item) => !["completed", "cancelled", "failed", "abandoned"].includes(item.status));
  return `
    ${projectHeader(project)}
    <div class="workspace-summary-grid">
      ${metric("Открытые Work", open.length, open.length ? `${liveCount} live · ${open.length - liveCount} non-live` : "активной работы нет")}
      ${metric("Нужно внимания", attention.length, attention.length ? "есть actionable сигналы" : "всё спокойно")}
      ${metric("Managed Tasks", activeTasks.length, activeTasks.length ? "active / blocked" : "нет активных")}
      ${metric("Epics", activeEpics.length, activeEpics.length ? "в работе" : "нет активных")}
    </div>
    ${attention.length ? `<div class="cockpit-attention">${attentionPanel(data)}</div>` : ""}
    <div class="dashboard-grid project-workspace-layout">
      <div class="dashboard-main">
        ${openWorkPanel(data)}
        ${recentResults(data)}
      </div>
      <div class="dashboard-side">
        ${workflowPanel(data)}
        ${knowledgePulse(data)}
        ${projectHealth(data)}
      </div>
    </div>`;
}

function groupedWork"""
project = regex_once(
    project,
    r"export function renderProject\(data\) \{.*?\n\}\n\nfunction groupedWork",
    render_project,
    "project cockpit render",
)
PROJECT.write_text(project, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")
if "/* Project Cockpit */" in css:
    raise RuntimeError("Project Cockpit CSS already applied")
css += r"""

/* Project Cockpit */
.cockpit-attention { margin-bottom: 18px; }
.cockpit-work-row { position: relative; padding-left: 10px; padding-right: 2px; }
.cockpit-work-row.is-focus::before {
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 0;
  width: 2px;
  border-radius: 2px;
  background: #8f82ec;
  content: "";
}
.cockpit-focus-label {
  margin-right: 7px;
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--accent-soft);
  color: #c9c1ff;
  font-size: 8.5px;
  letter-spacing: .04em;
}
.cockpit-workflow-panel .panel-header { margin-bottom: 2px; }
.cockpit-workflow-group { padding: 8px 0 4px; border-top: 1px solid var(--border); }
.cockpit-workflow-group:first-of-type { border-top: 0; }
.cockpit-workflow-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 14px 4px; }
.cockpit-workflow-head strong { color: var(--text-soft); font-size: 10.5px; }
.cockpit-workflow-head a { color: #9d92ef; font-size: 9.5px; }
.cockpit-workflow-panel .workspace-record-list { padding-top: 0; padding-bottom: 0; }
.cockpit-workflow-panel .workspace-record { padding: 8px 0; }
.cockpit-empty-line { padding: 7px 14px 10px; color: var(--muted-2); font-size: 10px; }

@media (max-width: 620px) {
  .cockpit-work-row { align-items: flex-start; }
  .cockpit-work-row .toolbar-controls { flex: 0 0 auto; }
}
"""
CSS.write_text(css, encoding="utf-8")
