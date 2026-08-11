import { escapeHtml } from "../format.js";
import { metric, stateBadge, timeline, scanLabel, taskSummary, stageName } from "../components/common.js";

function runtimePanel(data) {
  const s = data.summary || {};
  const service = data.service || {};
  const core = data.core_runtime || {};
  const db = data.database || {};
  const uptimeMinutes = Math.max(0, Math.floor(Number(service.uptime_seconds || 0) / 60));
  return `<section class="panel">
    <div class="panel-header"><div><div class="panel-title">Runtime health</div><div class="panel-hint">Persistent core, database и MCP transport</div></div>${stateBadge(db.connected && core.status !== "degraded" ? "healthy" : "warning")}</div>
    <div class="runtime-list">
      <div class="runtime-row"><span class="runtime-label">Core service</span><span class="runtime-value">${escapeHtml(core.status === "ready" ? "READY" : core.status || "—")}</span></div>
      <div class="runtime-row"><span class="runtime-label">Embeddings</span><span class="runtime-value">${escapeHtml(core.embeddings || "—")}</span></div>
      <div class="runtime-row"><span class="runtime-label">PostgreSQL</span><span class="runtime-value">${escapeHtml(db.connected ? "READY" : "UNAVAILABLE")}</span></div>
      <div class="runtime-row"><span class="runtime-label">Background service</span><span class="runtime-value">${escapeHtml(service.background ? `PID ${service.pid || "—"}` : "manual")}</span></div>
      <div class="runtime-row"><span class="runtime-label">Uptime</span><span class="runtime-value">${escapeHtml(service.background ? `${uptimeMinutes} мин` : "—")}</span></div>
      <div class="runtime-row"><span class="runtime-label">stdio bridges</span><span class="runtime-value">${escapeHtml(s.mcp_processes ?? 0)}</span></div>
      <div class="runtime-row"><span class="runtime-label">Protocol warnings</span><span class="runtime-value">${escapeHtml(s.protocol_warnings ?? 0)}</span></div>
    </div>
  </section>`;
}

export function renderOverview(data) {
  const s = data.summary || {};
  const dbReady = Boolean(data.database?.connected);
  const projects = data.projects || [];
  const core = data.core_runtime || {};
  const coreReady = core.status === "ready";
  return `
    ${!dbReady ? `<div class="alert">PostgreSQL недоступен. Панель показывает безопасный наблюдаемый state, но memory/task операции могут быть недоступны.</div>` : ""}
    <div class="summary-grid">
      ${metric("Проекты", s.projects ?? 0, "зарегистрировано в AI Layer")}
      ${metric("Активные Task", s.active_tasks ?? 0, s.attention_tasks ? `${s.attention_tasks} требуют решения пользователя` : s.blocked_tasks ? `${s.blocked_tasks} blocked` : "строго последовательно")}
      ${metric("Core runtime", coreReady ? "Готов" : core.status || "—", core.embeddings ? `embeddings: ${core.embeddings}` : "persistent local service")}
      ${metric("MCP p95", s.mcp_worst_project_p95_ms != null ? `${s.mcp_worst_project_p95_ms} мс` : "—", `${s.failures_5m ?? 0} rejected за 5 мин`)}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Проекты и текущая работа</div><div class="panel-hint">Task, stage и protocol state без лишних технических деталей</div></div><span class="muted">${projects.length} всего</span></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Проект</th><th>Состояние</th><th>Task</th><th>MCP</th><th>Stage</th><th>Memory</th></tr></thead>
              <tbody>
                ${projects.map((p) => `<tr class="project-row" data-project-key="${escapeHtml(p.key)}">
                  <td><div class="project-name">${escapeHtml(p.name)}</div><div class="project-root">${escapeHtml(p.root)}</div></td>
                  <td>${stateBadge(p.project_state || "healthy")}</td>
                  <td>${p.task ? `<div class="table-task-key">${escapeHtml(p.task.key || "—")}${p.task?.human_attention_required ? " · нужно решение" : p.task?.status === "blocked" ? " · blocked" : p.task_active ? " · active" : " · latest"}</div><div class="table-task-goal">${escapeHtml(p.task.goal || "—")}</div>` : `<span class="muted">нет</span>`}</td>
                  <td>${stateBadge(p.protocol_state?.status || "healthy")}<div class="protocol-note">${p.protocol_state?.failures_5m ? `${escapeHtml(p.protocol_state.failures_5m)} rejected${p.protocol_state.recovered ? " · recovered" : ""}` : "без recent failures"}</div></td>
                  <td>${escapeHtml(stageName(p.task?.active_stage?.kind))}${p.task?.open_findings ? `<div class="protocol-note">findings: ${escapeHtml(p.task.open_findings)}</div>` : ""}</td>
                  <td>${escapeHtml(scanLabel(p.last_scan))}</td>
                </tr>`).join("") || `<tr><td colspan="6"><div class="empty">Зарегистрированных проектов нет</div></td></tr>`}
              </tbody>
            </table>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последние Task</div><div class="panel-hint">Быстрый operational context по активным проектам</div></div><span class="muted">до 6</span></div>
          <div class="task-stack">${projects.filter((p) => p.task).slice(0, 6).map((p) => taskSummary(p.task, p.task_active)).join("") || `<div class="empty">Задач пока нет</div>`}</div>
        </section>
      </div>
      <div class="dashboard-side">
        ${runtimePanel(data)}
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последняя активность</div><div class="panel-hint">События MCP и core runtime</div></div><span class="muted">машина</span></div>
          ${timeline((data.recent_activity || []).slice(0, 14), true)}
        </section>
      </div>
    </div>`;
}
