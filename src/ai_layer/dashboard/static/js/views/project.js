import { age, escapeHtml } from "../format.js";
import { agentsList, metric, stageName, stateBadge, taskSummary, timeline } from "../components/common.js";
import { hashUrl, infoRow } from "../components/ui.js";

function nextAction(task, authoritativeNext) {
  const next = authoritativeNext || task?.next_action || {};
  const labels = {
    create_task: "Создать задачу",
    delegate_stage: "Делегировать стадию",
    record_stage_result: "Зафиксировать результат",
    unmanaged_stage_mutation: "Разобрать изменения",
    resolve_unmanaged_changes: "Разобрать изменения до Task",
    human_attention_required: "Нужно решение пользователя",
    done: "Завершено",
    none: "Нет действий",
  };
  return {
    label: labels[next.action] || next.action || "—",
    tool: next.tool || "—",
    code: next.code || null,
  };
}

function stageHistory(task) {
  const stages = task?.stages || [];
  if (!stages.length) return `<div class="empty">Истории стадий пока нет</div>`;
  return `<div class="stage-list">${stages.map((stage) => `
    <div class="stage-row ${escapeHtml(stage.status || "")}">
      <div class="stage-index">${escapeHtml(stage.ordinal)}</div>
      <div class="stage-body">
        <div class="stage-title">${escapeHtml(stageName(stage.kind))}${stage.review_round ? ` #${escapeHtml(stage.review_round)}` : stage.fix_round ? ` #${escapeHtml(stage.fix_round)}` : ""}</div>
        <div class="stage-summary">${escapeHtml(stage.summary || (stage.status === "active" ? "Активная стадия" : "—"))}</div>
        <div class="stage-foot">${stage.worker_id ? `worker ${escapeHtml(stage.worker_id)}` : "worker не привязан"}${stage.agent_policy?.profile ? ` · ${escapeHtml(stage.agent_policy.profile)}` : ""}${stage.model_identity?.actual ? ` · actual ${escapeHtml(stage.model_identity.actual)}` : stage.model_identity?.requested ? ` · requested ${escapeHtml(stage.model_identity.requested)}` : ""}${stage.model_identity?.assurance ? ` · ${escapeHtml(stage.model_identity.assurance)}` : ""}</div>
      </div>
      ${stateBadge(stage.status || "idle")}
    </div>`).join("")}</div>`;
}

function findings(task) {
  const items = task?.active_findings?.length ? task.active_findings : (task?.findings || []).filter((item) => item.status !== "verified");
  if (!items.length) return `<div class="empty">Активных замечаний review нет</div>`;
  return `<div class="finding-list">${items.slice(0, 10).map((item) => `
    <div class="finding ${escapeHtml(item.status || "")}">
      <div class="finding-head"><strong>${escapeHtml(item.severity || "medium")}</strong><span>${escapeHtml(item.status || "open")}</span></div>
      <div class="finding-problem">${escapeHtml(item.problem || "—")}</div>
      ${item.path ? `<div class="finding-path">${escapeHtml(item.path)}</div>` : ""}
      ${item.required_fix ? `<div class="finding-fix">Нужно: ${escapeHtml(item.required_fix)}</div>` : ""}
    </div>`).join("")}</div>`;
}

function skillsPanel(skillState, projectKey) {
  const observed = skillState?.last_context || {};
  const catalogs = skillState?.configured_catalog || {};
  const recent = [...(skillState?.observed_fetches || [])].reverse().slice(0, 6);
  return `<section class="panel">
    <div class="panel-header"><div><div class="panel-title">Скиллы</div><div class="panel-hint">Последние наблюдаемые retrieval, не скрытые решения host-а</div></div><a class="panel-header-link" href="${hashUrl("skills", { project: projectKey })}">Каталог →</a></div>
    <div class="skills-summary">
      <div class="skill-chip-row">${Object.entries(catalogs).map(([host, count]) => `<span class="skill-chip">${escapeHtml(host)} · ${escapeHtml(count)}</span>`).join("") || `<span class="muted">catalog не materialized</span>`}</div>
      <span class="skill-source-note">host-native routing · automatic injection ${observed.automatic_skill_injection ? "ON" : "OFF"}</span>
    </div>
    <div class="skill-on-demand-body">
      <div class="skill-list">${recent.length ? recent.map((item) => `<div class="skill-card"><div class="skill-card-top"><strong>${escapeHtml(item.slug)}</strong><span class="skill-chip ${item.full ? "" : "loaded"}">${escapeHtml(item.section || "full")}</span></div><div class="skill-reason">${escapeHtml(item.at ? age(item.at) : "")}</div></div>`).join("") : `<div class="empty compact">skill_get ещё не наблюдался</div>`}</div>
    </div>
  </section>`;
}

function projectLinks(projectKey) {
  return `<div class="project-actions">
    <a href="${hashUrl("tasks", { project: projectKey })}">Задачи</a>
    <a href="${hashUrl("epics", { project: projectKey })}">Эпики</a>
    <a href="${hashUrl("skills", { project: projectKey })}">Скиллы</a>
    <a href="${hashUrl("rules", { project: projectKey })}">Правила</a>
    <a href="${hashUrl("knowledge", { project: projectKey })}">База знаний</a>
    <a href="${hashUrl("activity", { project: projectKey })}">Активность</a>
  </div>`;
}

export function renderProject(data) {
  const project = data.project || {};
  const metrics = data.metrics || {};
  const task = project.task;
  const next = nextAction(task, project.next_action);
  const protocol = project.protocol_state || {};
  const activeStage = task?.active_stage;
  const intelligence = project.intelligence || {};
  const projectMap = intelligence.project_map || {};
  const freshness = intelligence.freshness || {};
  const focus = intelligence.current_focus || null;
  const focusLabel = focus ? `${focus.kind === "epic" ? "Epic" : "Task"} ${focus.key || ""}`.trim() : "Native / новая работа";
  return `
    <div class="project-head">
      <div><h2>${escapeHtml(project.name || "Проект")}</h2><div class="path">${escapeHtml(project.root || "")}</div></div>
      ${stateBadge(project.project_state || "healthy")}
    </div>
    ${projectLinks(project.key)}
    ${taskSummary(task, project.task_active)}
    <div class="summary-grid">
      ${metric("Текущая стадия", activeStage ? stageName(activeStage.kind) : "—", activeStage?.worker_id || "нет active worker")}
      ${metric("Следующее действие", next.label, next.tool !== "—" ? next.tool : (next.code || "navigator"))}
      ${metric("MCP p95", project.mcp_latency?.p95_ms != null ? `${project.mcp_latency.p95_ms} мс` : "—", project.mcp_latency?.p99_ms != null ? `p99 ${project.mcp_latency.p99_ms} мс` : "")}
      ${metric("Project Map", projectMap.navigation_files != null ? `${projectMap.navigation_files} файлов` : "—", `${escapeHtml(projectMap.symbol_count ?? "—")} symbols · ${escapeHtml(freshness.status || "unknown")}`)}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Цепочка выполнения</div><div class="panel-hint">Durable workflow выбранной Task</div></div>${task ? `<a class="panel-header-link" href="#/task/${encodeURIComponent(project.key)}/${encodeURIComponent(task.key)}">Детали Task →</a>` : ""}</div>
          ${stageHistory(task)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Замечания review</div><div class="panel-hint">До 10 actionable findings</div></div><span class="muted">${escapeHtml(task?.open_findings ?? 0)} открыто</span></div>
          ${findings(task)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Техническая активность</div><div class="panel-hint">Только 10 последних MCP/tool событий</div></div><a class="panel-header-link" href="${hashUrl("activity", { project: project.key })}">Все события →</a></div>
          ${timeline((data.timeline || []).slice(0, 10), false)}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Project Intelligence</div><div class="panel-hint">Рабочий контекст и карта проекта без terminal dump</div></div></div>
          <div class="info-list">
            ${infoRow("Current focus", focusLabel, focus?.title || "нет managed focus")}
            ${infoRow("Project Map", projectMap.navigation_files != null ? `${projectMap.navigation_files} файлов · ${projectMap.symbol_count ?? 0} symbols` : "недоступна", freshness.status || "unknown")}
            ${infoRow("Memory refresh", project.memory_refresh?.status || "idle")}
            ${infoRow("Execution owner", intelligence.execution_owner || "host-native")}
            ${infoRow("Protocol", protocol.status || "healthy", protocol.failures_5m ? `${protocol.failures_5m} failures / 5m${protocol.recovered ? " · recovered" : ""}` : "без recent failures")}
            ${infoRow("Privacy mode", project.mode || "standard")}
            ${infoRow("Events / 24h", metrics.events_24h ?? 0)}
            ${infoRow("Failures / 24h", metrics.failures_24h ?? 0)}
          </div>
          <details class="technical-details"><summary><span>Технические детали</span><span class="muted">identity · workflow</span></summary><div class="kv">
            <div class="kv-row"><span class="kv-key">Workflow profile</span><span>${escapeHtml(task?.workflow_profile || "—")}</span></div>
            <div class="kv-row"><span class="kv-key">Risk / cost</span><span>${escapeHtml(task?.risk_level || "—")} · ${escapeHtml(task?.cost_policy || "—")}</span></div>
            <div class="kv-row"><span class="kv-key">Execution origin</span><span>${escapeHtml(task?.execution_origin || "—")}</span></div>
            <div class="kv-row"><span class="kv-key">Map freshness</span><span>${escapeHtml(freshness.status || "—")}</span></div>
            <div class="kv-row"><span class="kv-key">Scan reason</span><span>${escapeHtml(project.scan_reason || "—")}</span></div>
            <div class="kv-row"><span class="kv-key">Last event</span><span>${escapeHtml(metrics.last_event_at ? age(metrics.last_event_at) : "никогда")}</span></div>
          </div></details>
        </section>
        ${skillsPanel(data.skill_state, project.key)}
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Подключённые агенты</div><div class="panel-hint">Живые MCP процессы этого проекта</div></div><span class="muted">${escapeHtml((project.agents || []).length)} сейчас</span></div>
          ${agentsList(project.agents || [])}
        </section>
      </div>
    </div>`;
}
