import { age, duration, escapeHtml, time } from "../format.js";
import { metric, stageName, stateBadge } from "../components/common.js";
import { compactList, filterTabs, hashUrl, infoRow, pagination, projectPicker } from "../components/ui.js";

function taskStage(task) {
  return task?.active_stage ? stageName(task.active_stage.kind) : task?.status === "completed" ? "Завершена" : "—";
}

function taskRows(items) {
  if (!items?.length) return `<div class="empty">Задач по выбранному фильтру нет</div>`;
  return `<div class="record-list">${items.map((task) => {
    const project = task.project || {};
    const findings = task.finding_summary || {};
    return `<a class="record-row" href="${hashUrl(`task/${project.key}/${task.key}`)}">
      <div class="record-primary">
        <div class="record-kicker">${escapeHtml(project.name || "Проект")} · ${escapeHtml(task.key || "Task")}</div>
        <div class="record-title">${escapeHtml(task.goal || "—")}</div>
        <div class="record-meta">${escapeHtml(taskStage(task))} · ${escapeHtml(task.workflow_profile || "standard")} · ${escapeHtml(task.risk_level || "normal")}${findings.open || findings.pending_verification ? ` · findings ${escapeHtml((findings.open || 0) + (findings.pending_verification || 0))}` : ""}</div>
      </div>
      <div class="record-side">
        ${stateBadge(task.status || "idle")}
        <span class="record-time">${escapeHtml(task.updated_at ? age(task.updated_at) : "")}</span>
      </div>
    </a>`;
  }).join("")}</div>`;
}

export function renderTasks(payload, route) {
  const filters = payload.filters || {};
  const project = filters.project_key || route.project || null;
  const status = filters.status || route.status || "";
  const path = "tasks";
  const params = { project, status };
  return `
    <div class="page-toolbar">
      <div>
        <div class="section-eyebrow">WORKFLOW</div>
        <div class="section-heading">История и текущая работа</div>
      </div>
      <div class="toolbar-controls">
        ${projectPicker(payload.projects || [], project, path, { status })}
      </div>
    </div>
    <section class="panel">
      <div class="panel-header panel-header-wrap">
        <div><div class="panel-title">Задачи</div><div class="panel-hint">По 10 записей. Детали стадий, review и verification открываются отдельно.</div></div>
        ${filterTabs([
          { label: "Все", value: "" },
          { label: "Активные", value: "active" },
          { label: "Blocked", value: "blocked" },
          { label: "Завершённые", value: "completed" },
          { label: "Отменённые", value: "cancelled" },
        ], status, path, { project }, "status")}
      </div>
      ${taskRows(payload.items || [])}
      <div class="panel-footer">
        <span class="muted">${escapeHtml(payload.pagination?.total || 0)} всего</span>
        ${pagination(payload.pagination, path, params)}
      </div>
    </section>`;
}

function stageTimeline(task) {
  const stages = task?.stages || [];
  if (!stages.length) return `<div class="empty">Истории стадий нет</div>`;
  return `<div class="stage-list">${stages.map((stage) => `
    <div class="stage-row ${escapeHtml(stage.status || "")}">
      <div class="stage-index">${escapeHtml(stage.ordinal)}</div>
      <div class="stage-body">
        <div class="stage-title">${escapeHtml(stageName(stage.kind))}${stage.review_round ? ` #${escapeHtml(stage.review_round)}` : stage.fix_round ? ` #${escapeHtml(stage.fix_round)}` : ""}</div>
        <div class="stage-summary">${escapeHtml(stage.summary || (stage.status === "active" ? "Стадия выполняется" : "—"))}</div>
        <div class="stage-foot">${stage.worker_id ? `worker ${escapeHtml(stage.worker_id)}` : "worker не привязан"}${stage.agent_policy?.profile ? ` · ${escapeHtml(stage.agent_policy.profile)}` : ""}${stage.model_identity?.actual ? ` · actual ${escapeHtml(stage.model_identity.actual)}` : stage.model_identity?.requested ? ` · requested ${escapeHtml(stage.model_identity.requested)}` : ""}${stage.model_identity?.assurance ? ` · ${escapeHtml(stage.model_identity.assurance)}` : ""}</div>
      </div>
      ${stateBadge(stage.status || "idle")}
    </div>`).join("")}</div>`;
}

function findings(task) {
  const items = task?.findings || [];
  if (!items.length) return `<div class="empty">Review findings отсутствуют</div>`;
  const visible = [...items].slice(-10).reverse();
  return `<div class="finding-list">${visible.map((item) => `
    <div class="finding ${escapeHtml(item.status || "")}">
      <div class="finding-head"><strong>${escapeHtml(item.severity || "medium")}</strong><span>${escapeHtml(item.status || "open")}</span></div>
      <div class="finding-problem">${escapeHtml(item.problem || "—")}</div>
      ${item.path ? `<div class="finding-path">${escapeHtml(item.path)}</div>` : ""}
      ${item.required_fix ? `<div class="finding-fix">Нужно: ${escapeHtml(item.required_fix)}</div>` : ""}
    </div>`).join("")}${items.length > 10 ? `<div class="table-caption">Показаны 10 последних из ${escapeHtml(items.length)}</div>` : ""}</div>`;
}

function verification(items) {
  if (!items?.length) return `<div class="empty">Verification запусков нет</div>`;
  return `<div class="verification-list">${items.slice(0, 10).map((item) => {
    const command = (item.command || []).join(" ") || "—";
    const ok = item.exit_code === 0 && !item.timed_out;
    return `<div class="verification-row">
      <div class="verification-main">
        <div class="verification-command">${escapeHtml(command)}</div>
        <div class="verification-meta">${escapeHtml(item.assurance || "—")} · ${escapeHtml(item.completed_at ? age(item.completed_at) : "")}${item.output_summary ? ` · ${escapeHtml(item.output_summary)}` : ""}</div>
      </div>
      ${stateBadge(ok ? "completed" : "warning")}
    </div>`;
  }).join("")}</div>`;
}

export function renderTaskDetail(payload) {
  const task = payload.task || {};
  const project = payload.project || {};
  const findingSummary = task.finding_summary || {};
  return `
    <div class="detail-hero">
      <div>
        <a class="back-link" href="#/tasks">← Все задачи</a>
        <div class="detail-kicker">${escapeHtml(project.name || "Проект")} · ${escapeHtml(task.key || "Task")}</div>
        <h2>${escapeHtml(task.goal || "—")}</h2>
        <div class="detail-subtitle">${escapeHtml(task.workflow_profile || "standard")} · создана ${escapeHtml(task.created_at ? age(task.created_at) : "—")}</div>
      </div>
      ${stateBadge(task.status || "idle")}
    </div>
    ${task.human_attention_required ? `<div class="notice warning"><strong>Нужно решение пользователя.</strong> ${escapeHtml(task.human_attention_reason || task.blocked_reason || "")}</div>` : task.blocked_reason ? `<div class="notice warning">${escapeHtml(task.blocked_reason)}</div>` : ""}
    <div class="summary-grid">
      ${metric("Текущая стадия", taskStage(task), task.active_stage?.worker_id || "нет active worker")}
      ${metric("Риск", task.risk_level || "normal", (task.risk_reasons || []).slice(0, 2).join(" · "))}
      ${metric("Политика стоимости", task.cost_policy || "economy", `${task.agent_usage?.delegated_stages || 0} delegated stage(s)`)}
      ${metric("Review findings", (findingSummary.open || 0) + (findingSummary.pending_verification || 0), `${findingSummary.verified || 0} verified`)}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Цепочка выполнения</div><div class="panel-hint">Полная durable история стадий этой Task</div></div><span class="muted">${escapeHtml((task.stages || []).length)} стадий</span></div>
          ${stageTimeline(task)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Review findings</div><div class="panel-hint">Не более 10 последних замечаний</div></div><span class="muted">${escapeHtml(findingSummary.total || 0)} всего</span></div>
          ${findings(task)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Verification</div><div class="panel-hint">Последние 10 реальных запусков проверок для этой задачи</div></div><span class="muted">${escapeHtml((payload.verification || []).length)} записей</span></div>
          ${verification(payload.verification || [])}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Контракт задачи</div><div class="panel-hint">То, что задача должна выполнить и сохранить</div></div></div>
          <div class="content-block"><h3>Acceptance criteria</h3>${compactList(task.acceptance_criteria, "Не заданы")}</div>
          <div class="content-block"><h3>Constraints</h3>${compactList(task.constraints, "Не заданы")}</div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Сводка выполнения</div><div class="panel-hint">Без внутреннего prompt payload</div></div></div>
          <div class="info-list">
            ${infoRow("Происхождение", task.execution_origin || "managed")}
            ${infoRow("Review rounds", task.review_round ?? 0)}
            ${infoRow("Fix rounds", task.fix_round ?? 0)}
            ${infoRow("Изменённых файлов", task.final_changes?.total ?? task.final_changes?.files?.length ?? 0)}
            ${infoRow("Pre-existing changes", task.preexisting_changes?.total ?? 0)}
            ${infoRow("Adopted changes", task.adopted_changes?.total ?? 0)}
          </div>
          ${task.completion_summary ? `<div class="content-block"><h3>Completion summary</h3><p>${escapeHtml(task.completion_summary)}</p></div>` : ""}
        </section>
      </div>
    </div>`;
}

function lastScan(projects) {
  const values = (projects || []).map((project) => project.last_scan).filter(Boolean).sort();
  return values.length ? age(values[values.length - 1]) : "никогда";
}

function readinessLabel(value) {
  if (value === null || value === undefined) return "—";
  return value ? "Готов" : "Проблема";
}

function providerDiagnostics(diag) {
  const selected = diag?.project || null;
  const providers = selected?.providers?.length ? selected.providers : (diag?.global?.providers || []);
  const title = selected ? selected.name : "Глобальная установка";
  if (!providers.length) return `<div class="empty">Диагностика интеграций недоступна</div>`;
  return `<div class="info-list">${providers.slice(0, 10).map((provider) => {
    const details = [
      `bootstrap ${readinessLabel(provider.bootstrap_ready)}`,
      `MCP ${readinessLabel(provider.mcp_ready)}`,
      `skills ${readinessLabel(provider.native_skills_ready)}`,
    ];
    if (provider.runtime_acceptance_required) details.push("нужен runtime acceptance");
    return infoRow(provider.name, provider.ready ? "Готов" : "Внимание", details.join(" · "));
  }).join("")}</div>
  ${selected ? `<div class="panel-footer"><span class="muted">${escapeHtml(title)} · template v${escapeHtml(selected.template_version ?? "—")} · MCP executable ${selected.mcp_executable_ready ? "готов" : "не готов"}</span>${stateBadge(selected.ready ? "healthy" : "warning")}</div>` : `<div class="panel-footer"><span class="muted">${escapeHtml(title)}</span>${stateBadge(diag?.global?.ready ? "healthy" : "warning")}</div>`}`;
}

export function renderMonitoring(data, route) {
  const s = data.summary || {};
  const service = data.service || {};
  const core = data.core_runtime || {};
  const db = data.database || {};
  const projects = data.projects || [];
  const visibleProjects = projects.slice(0, 10);
  const diag = data.integration_monitoring || {};
  const selectedProject = route?.project || diag.project?.key || null;
  return `
    <div class="page-toolbar">
      <div><div class="section-eyebrow">RUNTIME & INTEGRATIONS</div><div class="section-heading">Состояние локальной системы</div></div>
      <div class="toolbar-controls">${projectPicker(diag.projects || [], selectedProject, "monitoring")}</div>
    </div>
    <div class="summary-grid six">
      ${metric("Core runtime", core.status === "ready" ? "Готов" : core.status || "—", core.embeddings ? `embeddings: ${core.embeddings}` : "persistent service")}
      ${metric("PostgreSQL", db.connected ? "Готов" : "Недоступен", db.pgvector ? "pgvector готов" : "pgvector —")}
      ${metric("MCP bridges", s.mcp_processes ?? 0, `${s.active_agents ?? 0} активных`)}
      ${metric("MCP p95", s.mcp_worst_project_p95_ms != null ? `${s.mcp_worst_project_p95_ms} мс` : "—", "worst project")}
      ${metric("Protocol warnings", s.protocol_warnings ?? 0, `${s.failures_5m ?? 0} failures за 5 мин`)}
      ${metric("Последний scan", lastScan(projects), `${projects.length} проектов`)}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Проекты</div><div class="panel-hint">Runtime, MCP и memory сигналы; максимум 10 строк</div></div><span class="muted">${escapeHtml(projects.length)} всего</span></div>
          <div class="table-wrap"><table><thead><tr><th>Проект</th><th>Runtime</th><th>MCP p95 / p99</th><th>Memory</th><th>Task</th></tr></thead><tbody>
            ${visibleProjects.map((project) => `<tr><td><a class="table-link" href="#/project/${encodeURIComponent(project.key)}"><div class="project-name">${escapeHtml(project.name)}</div><div class="project-root">${escapeHtml(project.root)}</div></a></td><td>${stateBadge(project.project_state || "healthy")}</td><td>${escapeHtml(project.mcp_latency?.p95_ms != null ? `${project.mcp_latency.p95_ms} / ${project.mcp_latency.p99_ms ?? "—"} мс` : "—")}</td><td>${escapeHtml(project.memory_refresh?.status || "idle")} · ${escapeHtml(project.last_scan ? age(project.last_scan) : "scan отсутствует")}</td><td>${project.task ? `${escapeHtml(project.task.key)} · ${escapeHtml(taskStage(project.task))}` : `<span class="muted">нет</span>`}</td></tr>`).join("") || `<tr><td colspan="5"><div class="empty">Нет проектов</div></td></tr>`}
          </tbody></table></div>
          ${projects.length > 10 ? `<div class="table-caption">Показаны 10 из ${escapeHtml(projects.length)} проектов</div>` : ""}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">IDE-интеграции</div><div class="panel-hint">Cursor / Codex / Antigravity: bootstrap, MCP и native skills без чтения конфигов в UI</div></div></div>
          ${providerDiagnostics(diag)}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Служба</div><div class="panel-hint">Локальный background runtime</div></div>${stateBadge(service.pid ? "healthy" : "warning")}</div>
          <div class="info-list">
            ${infoRow("Режим", service.background ? "background" : "manual")}
            ${infoRow("PID", service.pid || "—")}
            ${infoRow("Uptime", service.uptime_seconds != null ? `${Math.floor(service.uptime_seconds / 60)} мин` : "—")}
            ${infoRow("Version", data.version || "—")}
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Протокол</div><div class="panel-hint">Ошибки transport не маскируются как ошибки проекта</div></div></div>
          <div class="info-list">
            ${infoRow("Warnings", s.protocol_warnings ?? 0)}
            ${infoRow("Recovered", s.recovered_protocol_warnings ?? 0)}
            ${infoRow("Failures / 5 мин", s.failures_5m ?? 0)}
          </div>
        </section>
      </div>
    </div>`;
}

export function renderActivity(payload, route) {
  const project = payload.project_key || route.project || null;
  const params = { project };
  const items = payload.items || [];
  return `
    <div class="page-toolbar">
      <div><div class="section-eyebrow">OBSERVABILITY</div><div class="section-heading">Техническая активность</div></div>
      <div class="toolbar-controls">${projectPicker(payload.projects || [], project, "activity")}</div>
    </div>
    <section class="panel">
      <div class="panel-header"><div><div class="panel-title">События</div><div class="panel-hint">По 10 записей на страницу. Prompt/source payload не отображается.</div></div><span class="muted">${escapeHtml(payload.pagination?.total || 0)} за окно</span></div>
      ${items.length ? `<div class="activity-list">${items.map((item) => `<div class="activity-row">
        <div class="activity-status ${escapeHtml(item.status || "")}"></div>
        <div class="activity-time">${escapeHtml(item.ts ? time(item.ts) : "—")}</div>
        <div class="activity-main"><div class="activity-title">${escapeHtml(item.operation || "unknown")}</div><div class="activity-meta">${escapeHtml(item.project_name || "—")} · ${escapeHtml(item.client || "unknown")} · ${escapeHtml(item.category || "unknown")}${item.error_type ? ` · ${escapeHtml(item.error_type)}` : ""}</div></div>
        <div class="activity-duration">${escapeHtml(duration(item.duration_ms))}</div>
      </div>`).join("")}</div>` : `<div class="empty">Активности нет</div>`}
      <div class="panel-footer"><span class="muted">${escapeHtml(payload.retention || "")}</span>${pagination(payload.pagination, "activity", params)}</div>
    </section>`;
}
