import { age, escapeHtml } from "../format.js";
import { metric, scanLabel, stageName, stateBadge, taskSummary, timeline } from "../components/common.js";

function latestScan(projects) {
  const values = (projects || []).map((project) => project.last_scan).filter(Boolean).sort();
  return values.length ? age(values[values.length - 1]) : "никогда";
}

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
  if (!items.length) return `<div class="empty">Задач пока нет</div>`;
  return `<div class="task-stack">${items.map((project) => `<a class="task-link-wrap" href="#/task/${encodeURIComponent(project.key)}/${encodeURIComponent(project.task.key)}">${taskSummary(project.task, project.task_active)}</a>`).join("")}</div>`;
}

function quickLinks() {
  return `<div class="quick-grid">
    <a class="quick-card" href="#/skills"><span class="quick-icon">◇</span><div><strong>Скиллы</strong><span>Краткий каталог и полный content</span></div><span>→</span></a>
    <a class="quick-card" href="#/rules"><span class="quick-icon">≡</span><div><strong>Правила</strong><span>Global policy и project rules</span></div><span>→</span></a>
    <a class="quick-card" href="#/knowledge"><span class="quick-icon">▤</span><div><strong>База знаний</strong><span>Verified / Draft / Stale</span></div><span>→</span></a>
    <a class="quick-card" href="#/activity"><span class="quick-icon">↻</span><div><strong>Активность</strong><span>Последние технические операции</span></div><span>→</span></a>
  </div>`;
}

export function renderOverview(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const core = data.core_runtime || {};
  const dbReady = Boolean(data.database?.connected);
  return `
    ${!dbReady ? `<div class="notice danger">PostgreSQL недоступен. Dashboard остаётся read-only, но memory/task данные могут быть неполными.</div>` : ""}
    <div class="summary-grid six">
      ${metric("Проекты", summary.projects ?? 0, "зарегистрировано локально")}
      ${metric("Активные задачи", summary.active_tasks ?? 0, summary.attention_tasks ? `${summary.attention_tasks} требуют решения` : summary.blocked_tasks ? `${summary.blocked_tasks} blocked` : "workflow идёт штатно")}
      ${metric("Core runtime", core.status === "ready" ? "Готов" : core.status || "—", core.embeddings ? `embeddings: ${core.embeddings}` : "persistent service")}
      ${metric("MCP p95", summary.mcp_worst_project_p95_ms != null ? `${summary.mcp_worst_project_p95_ms} мс` : "—", "худший проект")}
      ${metric("Warnings", summary.protocol_warnings ?? 0, `${summary.failures_5m ?? 0} failures за 5 мин`)}
      ${metric("Memory scan", latestScan(projects), `${projects.length} проектов`)}
    </div>
    <div class="dashboard-grid overview-layout">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Проекты и текущая работа</div><div class="panel-hint">Компактный срез: максимум 10 проектов на overview</div></div><span class="muted">${escapeHtml(projects.length)} всего</span></div>
          ${projectTable(projects)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последние Task</div><div class="panel-hint">До четырёх задач; полная история вынесена в отдельный экран</div></div><a class="panel-header-link" href="#/tasks">Все задачи →</a></div>
          ${currentWork(projects)}
        </section>
      </div>
      <div class="dashboard-side">
        ${runtimePanel(data)}
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Рабочие разделы</div><div class="panel-hint">То, что раньше приходилось смотреть через CLI/MCP</div></div></div>
          ${quickLinks()}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последняя активность</div><div class="panel-hint">Только 10 последних событий</div></div><a class="panel-header-link" href="#/activity">Все события →</a></div>
          ${timeline((data.recent_activity || []).slice(0, 10), true)}
        </section>
      </div>
    </div>`;
}
