import { escapeHtml } from "../format.js";
import { metric, scanLabel, stateBadge, timeline } from "../components/common.js";
import { collectPortfolioWork, primaryProjectWork, workAttentionReason, workHref, workStack } from "./work.js";

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
      const work = primaryProjectWork(project);
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

function focusStrip(data, portfolio) {
  const summary = data.summary || {};
  const first = (portfolio.now || [])[0];
  const work = first?.work || null;
  const activeProject = first?.project || null;
  const attention = Number(portfolio.attentionTotal || 0) + Number(summary.attention_tasks || 0);
  const healthy = Boolean(data.database?.connected) && data.core_runtime?.status !== "degraded" && !attention;
  const title = work ? `${work.key || "Work"} · ${work.goal || "Текущая работа"}` : "Нет активной работы";
  const copy = work ? `${activeProject.name} · ${work.kind || "work"} · live` : "AI Layer ожидает следующую пользовательскую работу";
  return `<section class="focus-strip">
    <div class="focus-main">
      <div class="focus-label">Сейчас</div>
      <div class="focus-title">${escapeHtml(title)}</div>
      <div class="focus-copy">${escapeHtml(copy)}</div>
      <div class="focus-actions">
        ${work ? `<a class="text-link" href="${workHref(activeProject.key, work.key)}">Открыть работу →</a>` : ""}
        <a class="text-link" href="#/work">Все WorkItems →</a>
        <a class="text-link" href="#/tasks">Managed Tasks →</a>
        <a class="text-link" href="#/epics">Эпики →</a>
      </div>
    </div>
    <div class="focus-side">
      <div class="focus-label">Система</div>
      <div class="focus-signals">
        <div class="focus-signal"><span>Общее состояние</span><strong>${healthy ? "Норма" : attention ? "Нужно внимание" : "Проверить runtime"}</strong></div>
        <div class="focus-signal"><span>Live Work</span><strong>${escapeHtml(summary.active_work ?? portfolio.nowTotal ?? 0)}</strong></div>
        <div class="focus-signal"><span>Нужно внимание</span><strong>${escapeHtml(portfolio.attentionTotal ?? 0)}</strong></div>
        <div class="focus-signal"><span>Активные MCP bridges</span><strong>${escapeHtml(summary.active_mcp_bridges ?? 0)}</strong></div>
      </div>
    </div>
  </section>`;
}

function portfolioPanels(portfolio) {
  return `<div class="portfolio-grid">
    <section class="panel">
      <div class="panel-header"><div><div class="panel-title">Сейчас</div><div class="panel-hint">Только live WorkItems с non-stale AgentRun</div></div><a class="panel-header-link" href="#/work">Все →</a></div>
      ${workStack(portfolio.now, "Сейчас не наблюдается активной пользовательской работы", null, { total: portfolio.nowTotal })}
    </section>
    <section class="panel">
      <div class="panel-header"><div><div class="panel-title">Нужно внимание</div><div class="panel-hint">Blocked, stale-active и map pending/deferred</div></div><a class="panel-header-link" href="#/work">Все →</a></div>
      ${workStack(portfolio.attention, "Нет работы, требующей внимания", workAttentionReason, { total: portfolio.attentionTotal })}
    </section>
    <section class="panel">
      <div class="panel-header"><div><div class="panel-title">Недавно завершено</div><div class="panel-hint">Последние terminal WorkItems по проектам</div></div><a class="panel-header-link" href="#/work">Все →</a></div>
      ${workStack(portfolio.recent, "Недавних завершённых WorkItems нет", null, { total: portfolio.recentTotal })}
    </section>
  </div>`;
}

export function renderOverview(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const dbReady = Boolean(data.database?.connected);
  const portfolio = collectPortfolioWork(projects);
  return `
    ${!dbReady ? `<div class="notice danger">PostgreSQL недоступен. Dashboard остаётся read-only, но durable work/task данные могут быть неполными.</div>` : ""}
    ${focusStrip(data, portfolio)}
    <div class="summary-grid">
      ${metric("Проекты", summary.projects ?? 0, "зарегистрировано локально")}
      ${metric("Live Work", summary.active_work ?? 0, `${portfolio.attentionTotal || 0} нужно внимание`)}
      ${metric("MCP p95", summary.mcp_worst_project_p95_ms != null ? `${summary.mcp_worst_project_p95_ms} мс` : "—", "худший проект")}
      ${metric("Warnings", summary.protocol_warnings ?? 0, `${summary.failures_5m ?? 0} failures за 5 мин`)}
    </div>
    ${portfolioPanels(portfolio)}
    <div class="dashboard-grid overview-layout">
      <div class="dashboard-main">
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
