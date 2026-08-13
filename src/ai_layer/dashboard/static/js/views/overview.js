import { age, escapeHtml } from "../format.js";
import { metric, scanLabel, stateBadge, timeline } from "../components/common.js";

function runtimePanel(data) {
  const summary = data.summary || {};
  const service = data.service || {};
  const core = data.core_runtime || {};
  const db = data.database || {};
  return `<section class="panel">
    <div class="panel-header"><div><div class="panel-title">Состояние runtime</div><div class="panel-hint">Только сигналы, влияющие на текущую работу</div></div>${stateBadge(db.connected && core.status !== "degraded" ? "healthy" : "warning")}</div>
    <div class="info-list">
      <div class="info-row"><div><div class="info-label">Core service</div><div class="info-note">persistent local runtime</div></div><div class="info-value">${escapeHtml(core.status === "ready" ? "READY" : core.status || "—")}</div></div>
      <div class="info-row"><div><div class="info-label">PostgreSQL</div><div class="info-note">${db.pgvector ? "pgvector ready" : "vector status —"}</div></div><div class="info-value">${escapeHtml(db.connected ? "READY" : "UNAVAILABLE")}</div></div>
      <div class="info-row"><div><div class="info-label">Background service</div><div class="info-note">${service.background ? "system-managed" : "manual"}</div></div><div class="info-value">${escapeHtml(service.pid ? `PID ${service.pid}` : "—")}</div></div>
      <div class="info-row"><div><div class="info-label">MCP bridges</div><div class="info-note">${escapeHtml(summary.active_mcp_bridges ?? 0)} активных</div></div><div class="info-value">${escapeHtml(summary.mcp_processes ?? 0)}</div></div>
    </div>
    <a class="panel-link" href="#/monitoring">Открыть мониторинг →</a>
  </section>`;
}

function primaryWork(project) {
  const work = project.work || {};
  return (work.live || [])[0] || (work.active || [])[0] || (work.recent || [])[0] || null;
}

function mapLabel(project) {
  const map = project.project_map || {};
  const current = Number(map.semantic_current || 0);
  const missing = Number(map.semantic_missing || 0);
  const stale = Number(map.semantic_stale || 0);
  const coverage = Number(map.semantic_current_coverage || 0);
  if (!current && !missing && !stale) return "—";
  return `${Math.round(coverage * 100)}% · ${current}/${current + missing + stale}`;
}

function projectTable(projects) {
  const visible = (projects || []).slice(0, 10);
  if (!visible.length) return `<div class="empty">Зарегистрированных проектов нет</div>`;
  return `<div class="table-wrap"><table>
    <thead><tr><th>Проект</th><th>Состояние</th><th>Work</th><th>Managed Task</th><th>Project Map</th><th>MCP bridge</th><th>Scan</th></tr></thead>
    <tbody>${visible.map((project) => {
      const work = primaryWork(project);
      return `<tr class="project-row" data-project-key="${escapeHtml(project.key)}">
        <td><div class="project-name">${escapeHtml(project.name)}</div><div class="project-root">${escapeHtml(project.root)}</div></td>
        <td>${stateBadge(project.project_state || "healthy")}</td>
        <td>${work ? `<div class="table-task-key">${escapeHtml(work.key || "—")}</div><div class="table-task-goal">${escapeHtml(work.goal || "—")}</div>` : `<span class="muted">нет</span>`}</td>
        <td>${project.task ? `<div class="table-task-key">${escapeHtml(project.task.key || "—")}</div><div class="table-task-goal">${escapeHtml(project.task.goal || "—")}</div>` : `<span class="muted">нет</span>`}</td>
        <td>${escapeHtml(mapLabel(project))}</td>
        <td>${escapeHtml((project.mcp_bridges || []).length)}</td>
        <td>${escapeHtml(scanLabel(project.last_scan))}</td>
      </tr>`;
    }).join("")}</tbody>
  </table></div>${projects.length > 10 ? `<div class="table-caption">Показаны 10 из ${escapeHtml(projects.length)} проектов</div>` : ""}`;
}

function currentWork(projects) {
  const items = [];
  for (const project of projects || []) {
    for (const work of project.work?.live || []) items.push({ project, work });
  }
  if (!items.length) return `<div class="empty">Сейчас не наблюдается активной пользовательской работы</div>`;
  return `<div class="task-stack">${items.slice(0, 6).map(({ project, work }) => `<a class="task-link-wrap" href="#/project/${encodeURIComponent(project.key)}"><div class="task-summary"><div class="task-summary-top"><strong>${escapeHtml(work.key || "Work")}</strong>${stateBadge(work.status || "active")}</div><div class="task-summary-goal">${escapeHtml(work.goal || "—")}</div><div class="task-summary-meta">${escapeHtml(project.name)} · ${escapeHtml(work.kind || "work")} · ${escapeHtml(work.observability_coverage || "unknown coverage")}</div></div></a>`).join("")}</div>`;
}

function focusStrip(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const activeProject = projects.find((project) => (project.work?.live || []).length);
  const work = activeProject ? (activeProject.work.live || [])[0] : null;
  const attention = Number(summary.blocked_work || 0) + Number(summary.attention_tasks || 0);
  const healthy = Boolean(data.database?.connected) && data.core_runtime?.status !== "degraded" && !attention;
  const title = work ? `${work.key || "Work"} · ${work.goal || "Текущая работа"}` : "Нет активной работы";
  const copy = work ? `${activeProject.name} · ${work.kind || "work"} · ${work.status || "active"}` : "AI Layer ожидает следующую пользовательскую работу";
  return `<section class="focus-strip">
    <div class="focus-main">
      <div class="focus-label">Сейчас</div>
      <div class="focus-title">${escapeHtml(title)}</div>
      <div class="focus-copy">${escapeHtml(copy)}</div>
      <div class="focus-actions">
        ${work ? `<a class="text-link" href="#/project/${encodeURIComponent(activeProject.key)}">Открыть проект →</a>` : `<a class="text-link" href="#/activity">Журнал работы →</a>`}
        <a class="text-link" href="#/tasks">Managed Tasks →</a>
        <a class="text-link" href="#/epics">Эпики →</a>
      </div>
    </div>
    <div class="focus-side">
      <div class="focus-label">Система</div>
      <div class="focus-signals">
        <div class="focus-signal"><span>Общее состояние</span><strong>${healthy ? "Норма" : attention ? "Нужно внимание" : "Проверить runtime"}</strong></div>
        <div class="focus-signal"><span>Активная работа</span><strong>${escapeHtml(summary.active_work ?? 0)}</strong></div>
        <div class="focus-signal"><span>Blocked Work</span><strong>${escapeHtml(summary.blocked_work ?? 0)}</strong></div>
        <div class="focus-signal"><span>Активные MCP bridges</span><strong>${escapeHtml(summary.active_mcp_bridges ?? 0)}</strong></div>
      </div>
    </div>
  </section>`;
}

export function renderOverview(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const dbReady = Boolean(data.database?.connected);
  return `
    ${!dbReady ? `<div class="notice danger">PostgreSQL недоступен. Dashboard остаётся read-only, но durable work/task данные могут быть неполными.</div>` : ""}
    ${focusStrip(data)}
    <div class="summary-grid">
      ${metric("Проекты", summary.projects ?? 0, "зарегистрировано локально")}
      ${metric("Активная работа", summary.active_work ?? 0, summary.blocked_work ? `${summary.blocked_work} заблокировано` : "наблюдаемые WorkItems")}
      ${metric("MCP p95", summary.mcp_worst_project_p95_ms != null ? `${summary.mcp_worst_project_p95_ms} мс` : "—", "худший проект")}
      ${metric("Warnings", summary.protocol_warnings ?? 0, `${summary.failures_5m ?? 0} failures за 5 мин`)}
    </div>
    <div class="dashboard-grid overview-layout">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Текущая работа</div><div class="panel-hint">WorkItem отражает пользовательскую работу; Managed Task — отдельный уровень assurance</div></div><a class="panel-header-link" href="#/activity">Журнал →</a></div>
          ${currentWork(projects)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Проекты</div><div class="panel-hint">Work, managed workflow, Project Map и MCP bridge показываются раздельно</div></div><span class="muted">${escapeHtml(projects.length)} всего</span></div>
          ${projectTable(projects)}
        </section>
      </div>
      <div class="dashboard-side">
        ${runtimePanel(data)}
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последняя активность</div><div class="panel-hint">Диагностическая transport-активность; durable журнал доступен отдельно</div></div><a class="panel-header-link" href="#/activity">Все события →</a></div>
          ${timeline((data.recent_activity || []).slice(0, 10), true)}
        </section>
      </div>
    </div>`;
}
