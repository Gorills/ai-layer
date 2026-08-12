import { age, escapeHtml } from "../format.js";
import { metric, scanLabel, stageName, stateBadge, taskSummary, timeline } from "../components/common.js";

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
      <div class="info-row"><div><div class="info-label">MCP bridges</div><div class="info-note">${escapeHtml(summary.active_agents ?? 0)} активных</div></div><div class="info-value">${escapeHtml(summary.mcp_processes ?? 0)}</div></div>
    </div>
    <a class="panel-link" href="#/monitoring">Открыть мониторинг →</a>
  </section>`;
}

function projectTable(projects) {
  const visible = (projects || []).slice(0, 10);
  if (!visible.length) return `<div class="empty">Зарегистрированных проектов нет</div>`;
  return `<div class="table-wrap"><table>
    <thead><tr><th>Проект</th><th>Состояние</th><th>Task</th><th>Stage</th><th>MCP</th><th>Memory</th></tr></thead>
    <tbody>${visible.map((project) => `<tr class="project-row" data-project-key="${escapeHtml(project.key)}">
      <td><div class="project-name">${escapeHtml(project.name)}</div><div class="project-root">${escapeHtml(project.root)}</div></td>
      <td>${stateBadge(project.project_state || "healthy")}</td>
      <td>${project.task ? `<div class="table-task-key">${escapeHtml(project.task.key || "—")}</div><div class="table-task-goal">${escapeHtml(project.task.goal || "—")}</div>` : `<span class="muted">нет</span>`}</td>
      <td>${escapeHtml(stageName(project.task?.active_stage?.kind))}</td>
      <td>${escapeHtml(project.mcp_latency?.p95_ms != null ? `${project.mcp_latency.p95_ms} мс` : "—")}</td>
      <td>${escapeHtml(scanLabel(project.last_scan))}</td>
    </tr>`).join("")}</tbody>
  </table></div>${projects.length > 10 ? `<div class="table-caption">Показаны 10 из ${escapeHtml(projects.length)} проектов</div>` : ""}`;
}

function currentWork(projects) {
  const items = (projects || []).filter((project) => project.task).slice(0, 4);
  if (!items.length) return `<div class="empty">Активной и недавней работы пока нет</div>`;
  return `<div class="task-stack">${items.map((project) => `<a class="task-link-wrap" href="#/task/${encodeURIComponent(project.key)}/${encodeURIComponent(project.task.key)}">${taskSummary(project.task, project.task_active)}</a>`).join("")}</div>`;
}

function focusStrip(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const active = projects.find((project) => project.task_active && project.task) || projects.find((project) => project.task);
  const attention = Number(summary.attention_tasks || 0) + Number(summary.blocked_tasks || 0);
  const healthy = Boolean(data.database?.connected) && data.core_runtime?.status !== "degraded" && !attention;
  const title = active?.task
    ? `${active.task.key || "Task"} · ${active.task.goal || "Текущая задача"}`
    : "Нет активной Task";
  const copy = active?.task
    ? `${active.name} · ${stageName(active.task.active_stage?.kind)} · ${active.task.status || "idle"}`
    : "AI Layer ожидает следующую работу";
  return `<section class="focus-strip">
    <div class="focus-main">
      <div class="focus-label">Сейчас</div>
      <div class="focus-title">${escapeHtml(title)}</div>
      <div class="focus-copy">${escapeHtml(copy)}</div>
      <div class="focus-actions">
        ${active?.task ? `<a class="text-link" href="#/task/${encodeURIComponent(active.key)}/${encodeURIComponent(active.task.key)}">Открыть задачу →</a>` : `<a class="text-link" href="#/tasks">История задач →</a>`}
        <a class="text-link" href="#/epics">Эпики →</a>
      </div>
    </div>
    <div class="focus-side">
      <div class="focus-label">Система</div>
      <div class="focus-signals">
        <div class="focus-signal"><span>Общее состояние</span><strong>${healthy ? "Норма" : attention ? "Нужно внимание" : "Проверить runtime"}</strong></div>
        <div class="focus-signal"><span>Активные задачи</span><strong>${escapeHtml(summary.active_tasks ?? 0)}</strong></div>
        <div class="focus-signal"><span>Warnings</span><strong>${escapeHtml(summary.protocol_warnings ?? 0)}</strong></div>
        <div class="focus-signal"><span>Активные агенты</span><strong>${escapeHtml(summary.active_agents ?? 0)}</strong></div>
      </div>
    </div>
  </section>`;
}

export function renderOverview(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const dbReady = Boolean(data.database?.connected);
  return `
    ${!dbReady ? `<div class="notice danger">PostgreSQL недоступен. Dashboard остаётся read-only, но memory/task данные могут быть неполными.</div>` : ""}
    ${focusStrip(data)}
    <div class="summary-grid">
      ${metric("Проекты", summary.projects ?? 0, "зарегистрировано локально")}
      ${metric("Активные задачи", summary.active_tasks ?? 0, summary.attention_tasks ? `${summary.attention_tasks} требуют решения` : "текущая работа")}
      ${metric("MCP p95", summary.mcp_worst_project_p95_ms != null ? `${summary.mcp_worst_project_p95_ms} мс` : "—", "худший проект")}
      ${metric("Warnings", summary.protocol_warnings ?? 0, `${summary.failures_5m ?? 0} failures за 5 мин`)}
    </div>
    <div class="dashboard-grid overview-layout">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Текущая работа</div><div class="panel-hint">До четырёх Task без лишней технической детализации</div></div><a class="panel-header-link" href="#/tasks">Все задачи →</a></div>
          ${currentWork(projects)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Проекты</div><div class="panel-hint">Состояние workflow, MCP и memory</div></div><span class="muted">${escapeHtml(projects.length)} всего</span></div>
          ${projectTable(projects)}
        </section>
      </div>
      <div class="dashboard-side">
        ${runtimePanel(data)}
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последняя активность</div><div class="panel-hint">10 последних технических событий</div></div><a class="panel-header-link" href="#/activity">Все события →</a></div>
          ${timeline((data.recent_activity || []).slice(0, 10), true)}
        </section>
      </div>
    </div>`;
}
