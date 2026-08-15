import { age, duration, escapeHtml, time } from "../format.js";

const STATE_LABELS = {
  idle: "ОЖИДАНИЕ",
  active: "В РАБОТЕ",
  working: "РАБОТАЕТ",
  error: "ОШИБКА",
  warning: "ВНИМАНИЕ",
  healthy: "НОРМА",
  recovered: "ВОССТАНОВЛЕНО",
  blocked: "ЗАБЛОКИРОВАНО",
  attention: "НУЖНО РЕШЕНИЕ",
  none: "НЕТ",
  pending: "В ОЧЕРЕДИ",
  completed: "ГОТОВО",
  cancelled: "ОТМЕНЕНО",
  failed: "ОШИБКА",
  stale: "УСТАРЕЛО",
  interrupted: "ПРЕРВАНО",
  abandoned: "БРОШЕНО",
  draft: "ЧЕРНОВИК",
  approved: "СОГЛАСОВАНО",
  phase0: "PHASE 0",
  planning: "ПЛАНИРОВАНИЕ",
  running: "ВЫПОЛНЯЕТСЯ",
  final_review: "ФИНАЛЬНОЕ РЕВЬЮ",
  archived: "АРХИВ",
};

const STAGE_LABELS = {
  implement: "Исполнитель",
  discovery: "Исследование",
  review: "Ревьюер",
  fix: "Фиксер",
};

export function metric(label, value, note = "") {
  return `<div class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div>${note ? `<div class="metric-note">${escapeHtml(note)}</div>` : ""}</div>`;
}

export function stateBadge(state) {
  const normalized = String(state || "idle").toLowerCase();
  return `<span class="badge ${escapeHtml(normalized)}">${escapeHtml(STATE_LABELS[normalized] || normalized.toUpperCase())}</span>`;
}

export function stageName(kind) { return STAGE_LABELS[String(kind || "").toLowerCase()] || "—"; }

export function timeline(items, showProject = false) {
  if (!items?.length) return `<div class="empty">Недавней активности нет</div>`;
  const statusLabel = (value) => ({ completed: "успешно", failed: "отклонено" }[String(value || "").toLowerCase()] || value || "—");
  return `<ul class="timeline">${items.map((item) => {
    const normalized = Number(item.metrics?.normalization_count || 0);
    const extra = item.status === "failed" && item.error_type ? ` · ${escapeHtml(item.error_type)}` : normalized ? ` · нормализовано: ${escapeHtml(normalized)}` : "";
    return `
    <li class="timeline-item">
      <span class="timeline-time">${escapeHtml(time(item.ts))}</span>
      <div class="timeline-main">
        <div class="timeline-op">${escapeHtml(item.operation)}</div>
        <div class="timeline-meta">${showProject ? `${escapeHtml(item.project_name)} · ` : ""}${escapeHtml(item.client)} · ${escapeHtml(statusLabel(item.status))}${extra}</div>
      </div>
      <span class="timeline-duration">${escapeHtml(duration(item.duration_ms))}</span>
    </li>`;
  }).join("")}</ul>`;
}

export function agentsList(agents) {
  if (!agents?.length) return `<div class="empty">Нет MCP bridges</div>`;
  return `<div class="agent-list">${agents.map((agent) => `
    <div class="agent">
      <div class="agent-main">
        <div class="agent-name">${escapeHtml(agent.client || "неизвестно")}</div>
        <div class="agent-meta">сессия ${escapeHtml(String(agent.session_id || "—").slice(0, 12))}${agent.current_tool ? ` · ${escapeHtml(agent.current_tool)}` : ""}</div>
      </div>
      ${stateBadge(agent.activity_state || "idle")}
    </div>`).join("")}</div>`;
}

export function scanLabel(value) { return value ? age(value) : "никогда"; }

export function taskSummary(task, active = false) {
  if (!task) return `<div class="empty">Задач ещё не было</div>`;
  const stage = task.active_stage;
  const next = task.next_action || {};
  const pending = task.finding_summary?.pending_verification ?? 0;
  const open = task.finding_summary?.open ?? task.open_findings ?? 0;
  return `<div class="task-card ${task.status === "blocked" ? "task-blocked" : ""}">
    <div class="task-card-top">
      <div>
        <div class="task-key">${escapeHtml(task.key || "Задача")}${active ? " · активная" : ""}</div>
        <div class="task-goal">${escapeHtml(task.goal || "—")}</div>
      </div>
      ${stateBadge(task.status)}
    </div>
    <div class="task-meta">
      <span>Стадия: <strong>${escapeHtml(stageName(stage?.kind))}</strong></span>
      <span>Ревью: <strong>${escapeHtml(task.review_round ?? 0)}</strong></span>
      <span>Исправления: <strong>${escapeHtml(task.fix_round ?? 0)}</strong></span>
      <span>Нужно исправить: <strong>${escapeHtml(open)}</strong></span>
      <span>Ждут проверки: <strong>${escapeHtml(pending)}</strong></span>
    </div>
    ${task.human_attention_required ? `<div class="blocker"><strong>Автоцикл остановлен.</strong> ${escapeHtml(task.human_attention_reason || "Нужно решение пользователя.")}</div>` : ""}
    ${next.message ? `<div class="next-action"><span>Что сейчас:</span>${escapeHtml(next.message)}</div>` : ""}
    ${task.blocked_reason && !task.human_attention_required ? `<div class="blocker">${escapeHtml(task.blocked_reason)}</div>` : ""}
  </div>`;
}
