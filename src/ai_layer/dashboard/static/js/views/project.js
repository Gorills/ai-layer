import { age, escapeHtml } from "../format.js";
import { agentsList, metric, stateBadge, timeline, taskSummary, stageName } from "../components/common.js";

function operations(data) {
  const entries = Object.entries(data || {});
  if (!entries.length) return `<div class="empty">За последние 24 часа операций нет</div>`;
  const max = Math.max(...entries.map(([, value]) => Number(value) || 0), 1);
  return `<div class="ops">${entries.slice(0, 12).map(([name, count]) => `
    <div class="op-row">
      <div><div>${escapeHtml(name)}</div><div class="op-track"><div class="op-fill" style="width:${Math.max(4, Math.round((Number(count) / max) * 100))}%"></div></div></div>
      <div class="muted">${escapeHtml(count)}</div>
    </div>`).join("")}</div>`;
}

function nextAction(task, authoritativeNext) {
  const next = authoritativeNext || task?.next_action || {};
  const labels = {
    create_task: "Создать задачу",
    delegate_stage: "Делегировать стадию",
    record_stage_result: "Зафиксировать результат",
    unmanaged_stage_mutation: "Разобрать неуправляемые изменения",
    resolve_unmanaged_changes: "Разобрать изменения до задачи",
    human_attention_required: "Нужно решение пользователя",
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
        <div class="stage-summary">${escapeHtml(stage.summary || (stage.status === "active" ? "Ожидает выполнения делегированным worker" : "—"))}</div>
        <div class="stage-foot">${stage.worker_id ? `worker ${escapeHtml(stage.worker_id)} · ` : "не делегировано · "}${stage.agent_policy?.tier ? `${escapeHtml(stage.agent_policy.tier)} · ` : ""}${stage.agent_policy?.profile ? `${escapeHtml(stage.agent_policy.profile)} · ` : ""}${escapeHtml(stage.outcome || stage.status)}${stage.changes?.total != null ? ` · файлов изменено: ${escapeHtml(stage.changes.total)}` : ""}${stage.external_actions?.length ? ` · внешних действий: ${escapeHtml(stage.external_actions.length)}` : ""}</div>
      </div>
      ${stateBadge(stage.status)}
    </div>`).join("")}</div>`;
}

function findings(task) {
  const items = task?.active_findings?.length ? task.active_findings : (task?.findings || []);
  if (!items.length) return `<div class="empty">Активных замечаний ревьюера нет</div>`;
  return `<div class="finding-list">${items.map((item) => `
    <div class="finding ${escapeHtml(item.status || "")}">
      <div class="finding-head"><strong>${escapeHtml(item.severity || "medium")}</strong><span>${escapeHtml(item.status || "open")}</span></div>
      <div class="finding-problem">${escapeHtml(item.problem)}</div>
      ${item.path ? `<div class="finding-path">${escapeHtml(item.path)}</div>` : ""}
      ${item.required_fix ? `<div class="finding-fix">Нужно: ${escapeHtml(item.required_fix)}</div>` : ""}
    </div>`).join("")}</div>`;
}

function skillsPanel(skillState) {
  const observed = skillState?.last_context || {};
  const observedAt = observed.seen && observed.at ? age(observed.at) : null;
  const catalogs = skillState?.configured_catalog || {};
  const fetches = skillState?.observed_fetches || [];
  const recent = [...fetches].reverse();
  const catalogChips = Object.entries(catalogs)
    .map(([host, count]) => `<span class="skill-chip">${escapeHtml(host)} · ${escapeHtml(count)}</span>`)
    .join("");
  const fetchRows = recent.length
    ? recent.map((item) => `<div class="skill-card">
        <div class="skill-card-top"><strong>${escapeHtml(item.slug)}</strong><span class="skill-chip ${item.full ? "" : "loaded"}">${escapeHtml(item.section || "full")}</span></div>
        <div class="skill-reason">${item.full ? "Полный skill явно запрошен" : "Загружена конкретная секция"}${item.at ? ` · ${escapeHtml(age(item.at))}` : ""}</div>
      </div>`).join("")
    : `<div class="empty">В наблюдаемом окне skill_get ещё не вызывался</div>`;
  return `<section class="panel panel-accent skills-panel">
    <div class="panel-header">
      <div><div class="panel-title">Native Skills</div><div class="panel-hint">Релевантность определяет Cursor / Codex / Antigravity; AI Layer хранит content и наблюдает retrieval</div></div>
      <span class="muted">${escapeHtml(skillState?.task || "нет active Task")}</span>
    </div>
    <div class="skills-summary">
      <span class="skills-summary-label">Configured catalog:</span>
      <div class="skill-chip-row">${catalogChips || `<span class="muted">не materialized</span>`}</div>
      <span class="skill-source-note">Planner AI Layer: OFF · automatic domain injection: ${observed.automatic_skill_injection ? "ON" : "OFF"}${observedAt ? ` · context ${escapeHtml(observedAt)}` : ""}</span>
    </div>
    <div class="skill-on-demand-body">
      <div class="skill-tier-title" style="margin-bottom:10px">Фактически наблюдаемые skill_get</div>
      <div class="skill-list">${fetchRows}</div>
      <div class="skill-source-note" style="margin-top:10px">AI Layer не видит скрытое решение host-а: automatic vs manual activation остаётся HOST_HIDDEN.</div>
    </div>
  </section>`;
}

function projectDetails(p, task, next, m) {
  return `<details class="technical-details">
    <summary><span>Технические детали проекта</span><span class="muted">identity · memory · protocol</span></summary>
    <div class="kv">
      <div class="kv-row"><span class="kv-key">Состояние задачи</span><span>${escapeHtml(p.task_state || "none")}</span></div>
      <div class="kv-row"><span class="kv-key">Следующий tool</span><span>${escapeHtml(next.tool)}</span></div>
      <div class="kv-row"><span class="kv-key">Workflow code</span><span>${escapeHtml(next.code || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Workflow profile</span><span>${escapeHtml(task?.workflow_profile || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Risk / cost</span><span>${escapeHtml(task?.risk_level || "—")} · ${escapeHtml(task?.cost_policy || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Requested agent</span><span>${escapeHtml(task?.active_stage?.agent_policy?.profile || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Configured Cursor model</span><span>${escapeHtml(task?.active_stage?.agent_policy?.cursor_model || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Agent stages / strong</span><span>${escapeHtml(task?.agent_usage?.delegated_stages ?? 0)} / ${escapeHtml(task?.agent_usage?.strong_stages ?? 0)}</span></div>
      <div class="kv-row"><span class="kv-key">Происхождение Task</span><span>${escapeHtml(task?.execution_origin || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Принято внешних путей</span><span>${escapeHtml(task?.adopted_changes?.total ?? 0)}</span></div>
      <div class="kv-row"><span class="kv-key">Изменений до задачи</span><span>${escapeHtml(task?.preexisting_changes?.total ?? 0)}</span></div>
      <div class="kv-row"><span class="kv-key">MCP protocol</span><span>${escapeHtml(p.protocol_state?.status === "warning" ? (p.protocol_state?.recovered ? "warning · recovered" : "warning") : "healthy")}</span></div>
      <div class="kv-row"><span class="kv-key">Privacy mode</span><span>${escapeHtml(p.mode)}</span></div>
      <div class="kv-row"><span class="kv-key">Provenance</span><span>${escapeHtml(p.provenance)}</span></div>
      <div class="kv-row"><span class="kv-key">Файлов в памяти</span><span>${escapeHtml(p.scan_files ?? "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Причина скана</span><span>${escapeHtml(p.scan_reason || "—")}</span></div>
      <div class="kv-row"><span class="kv-key">Последнее событие</span><span>${escapeHtml(m.last_event_at ? age(m.last_event_at) : "никогда")}</span></div>
    </div>
  </details>`;
}

export function renderProject(data) {
  const p = data.project || {};
  const m = data.metrics || {};
  const task = p.task;
  const next = nextAction(task, p.next_action);
  const delegation = task?.active_stage?.worker_id ? task.active_stage.worker_id : (task?.active_stage ? "Не делегировано" : "—");
  const requestedAgent = task?.active_stage?.agent_policy?.profile || next?.agent_policy?.profile || null;
  const delegationNote = task?.active_stage?.worker_id ? `worker bound before mutation${requestedAgent ? ` · ${requestedAgent}` : ""}` : task?.active_stage ? `следующий шаг должен подтвердить navigator${requestedAgent ? ` · ${requestedAgent}` : ""}` : "нет active stage";
  const protocolLabel = p.protocol_state?.status === "warning" ? "Внимание" : "Норма";
  const protocolNote = p.protocol_state?.failures_5m ? `${p.protocol_state.failures_5m} отклонено${p.protocol_state.recovered ? " · восстановлено" : ""}` : "без recent failures";

  return `
    <div class="project-head">
      <div><h2>${escapeHtml(p.name)}</h2><div class="path">${escapeHtml(p.root)}</div></div>
      ${stateBadge(p.project_state || "healthy")}
    </div>
    ${taskSummary(task, p.task_active)}
    <div class="summary-grid">
      ${metric("Текущая стадия", task?.active_stage ? stageName(task.active_stage.kind) : "—", task?.active_stage?.status || "нет active stage")}
      ${metric("Следующее действие", next.label, next.tool !== "—" ? next.tool : (next.code || "authoritative navigator"))}
      ${metric("Делегирование", delegation, delegationNote)}
      ${metric("MCP protocol", protocolLabel, protocolNote)}
    </div>
    ${skillsPanel(data.skill_state)}
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Цепочка выполнения</div><div class="panel-hint">Adaptive workflow · одна active stage · cost-aware delegation</div></div><span class="muted">${escapeHtml(task?.workflow_profile || "—")} · ${escapeHtml(task?.risk_level || "—")}</span></div>
          ${stageHistory(task)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Замечания review</div><div class="panel-hint">Только текущий actionable lifecycle</div></div><span class="muted">${escapeHtml(task?.open_findings ?? 0)} открыто</span></div>
          ${findings(task)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Техническая активность</div><div class="panel-hint">MCP/tool события без prompt payload</div></div><span class="muted">24 часа</span></div>
          ${timeline(data.timeline || [], false)}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Подключённые агенты</div><div class="panel-hint">Живые MCP processes этого проекта</div></div><span class="muted">${escapeHtml((p.agents || []).length)} сейчас</span></div>
          ${agentsList(p.agents || [])}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Runtime & memory</div><div class="panel-hint">Сигналы, которые важны во время работы</div></div></div>
          <div class="runtime-list">
            <div class="runtime-row"><span class="runtime-label">Memory scan</span><span class="runtime-value">${escapeHtml(p.last_scan ? age(p.last_scan) : "никогда")}</span></div>
            <div class="runtime-row"><span class="runtime-label">Refresh queue</span><span class="runtime-value">${escapeHtml(p.memory_refresh?.status || "idle")}</span></div>
            <div class="runtime-row"><span class="runtime-label">MCP p95</span><span class="runtime-value">${escapeHtml(p.mcp_latency?.p95_ms != null ? `${p.mcp_latency.p95_ms} ms` : "—")}</span></div>
            <div class="runtime-row"><span class="runtime-label">MCP p99</span><span class="runtime-value">${escapeHtml(p.mcp_latency?.p99_ms != null ? `${p.mcp_latency.p99_ms} ms` : "—")}</span></div>
            <div class="runtime-row"><span class="runtime-label">Agent stages</span><span class="runtime-value">${escapeHtml(task?.agent_usage?.delegated_stages ?? 0)}</span></div>
            <div class="runtime-row"><span class="runtime-label">Strong requested</span><span class="runtime-value">${escapeHtml(task?.agent_usage?.strong_stages ?? 0)}</span></div>
            <div class="runtime-row"><span class="runtime-label">Findings pending verification</span><span class="runtime-value">${escapeHtml(task?.finding_summary?.pending_verification ?? 0)}</span></div>
          </div>
          ${projectDetails(p, task, next, m)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Операции AI Layer</div><div class="panel-hint">Частота вызовов по типам</div></div><span class="muted">24 часа</span></div>
          ${operations(m.operations)}
        </section>
      </div>
    </div>`;
}
