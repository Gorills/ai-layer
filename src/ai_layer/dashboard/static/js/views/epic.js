import { age, escapeHtml } from "../format.js";
import { stateBadge } from "../components/common.js";
import { filterTabs, hashUrl, infoRow, markdown, pagination, projectPicker } from "../components/ui.js";

function progressMarkup(progress) {
  const total = Number(progress?.total || 0);
  const completed = Number(progress?.completed || 0);
  if (!total) return `<div class="epic-row-version">plan не сформирован</div>`;
  const percent = Math.max(0, Math.min(100, Math.round((completed / total) * 100)));
  return `<div class="epic-progress">
    <div class="epic-progress-line"><div class="epic-progress-value" style="width:${percent}%"></div></div>
    <div class="epic-progress-label">${escapeHtml(completed)} / ${escapeHtml(total)} Task · ${escapeHtml(percent)}%</div>
  </div>`;
}

function plan(items, projectKey) {
  if (!items?.length) return `<div class="empty">Task plan появится после Phase 0</div>`;
  const visible = items.slice(0, 10);
  return `<div class="stage-list">${visible.map((item) => {
    const content = `
      <div class="stage-index">${escapeHtml(item.ordinal)}</div>
      <div class="stage-body">
        <div class="stage-title">${escapeHtml(item.title || item.key)}</div>
        <div class="stage-summary">${escapeHtml(item.goal || "—")}</div>
        <div class="stage-foot">${escapeHtml(item.kind)} · spec v${escapeHtml(item.spec_version)}${item.task_key ? ` · ${escapeHtml(item.task_key)} · ${escapeHtml(item.task_status || "—")}` : ""}</div>
      </div>
      ${stateBadge(item.status || "pending")}`;
    return item.task_key && projectKey
      ? `<a class="stage-row ${escapeHtml(item.status || "")}" href="#/task/${encodeURIComponent(projectKey)}/${encodeURIComponent(item.task_key)}">${content}</a>`
      : `<div class="stage-row ${escapeHtml(item.status || "")}">${content}</div>`;
  }).join("")}${items.length > 10 ? `<div class="table-caption">Показаны первые 10 из ${escapeHtml(items.length)} пунктов plan</div>` : ""}</div>`;
}

function audits(items, { compact = false } = {}) {
  if (!items?.length) return `<div class="empty">Аудитов пока нет</div>`;
  const limit = compact ? 3 : 10;
  const visible = [...items].reverse().slice(0, limit);
  return `<div class="finding-list ${compact ? "epic-mini-audits" : ""}">${visible.map((item) => `
    <div class="finding">
      <div class="finding-head"><strong>spec v${escapeHtml(item.spec_version)}</strong><span>${escapeHtml(item.scope || "independent")}</span></div>
      <div class="finding-problem">${escapeHtml(item.summary)}</div>
      <div class="finding-path">${escapeHtml(item.created_at ? age(item.created_at) : "")}${item.auditor_id ? ` · ${escapeHtml(item.auditor_id)}` : ""}</div>
      ${(item.findings || []).slice(0, compact ? 2 : 5).map((finding) => `<div class="finding-fix"><strong>${escapeHtml(finding.severity || "finding")}</strong> · ${escapeHtml(finding.problem || finding.summary || JSON.stringify(finding))}</div>`).join("")}
      ${(item.findings || []).length > (compact ? 2 : 5) ? `<div class="finding-path">Ещё ${escapeHtml(item.findings.length - (compact ? 2 : 5))} findings</div>` : ""}
    </div>`).join("")}${!compact && items.length > 10 ? `<div class="table-caption">Показаны 10 последних из ${escapeHtml(items.length)} аудитов</div>` : ""}</div>`;
}

function epicRows(items) {
  if (!items?.length) return `<div class="empty">Epics по выбранному фильтру не найдены</div>`;
  return `<div class="epic-list">${items.map((item) => `
    <a class="epic-row" href="#/epic/${encodeURIComponent(item.project?.key || item.project_key || "")}/${encodeURIComponent(item.key)}">
      <div class="epic-row-key">${escapeHtml(item.key)}</div>
      <div class="epic-row-main">
        <div class="epic-row-heading"><div class="epic-row-title">${escapeHtml(item.title || "Epic")}</div>${stateBadge(item.status || "draft")}</div>
        <div class="epic-row-meta">${escapeHtml(item.project?.name || "Проект")} · обновлён ${escapeHtml(item.updated_at ? age(item.updated_at) : "—")}${item.blocked_reason ? ` · ${escapeHtml(item.blocked_reason)}` : ""}</div>
      </div>
      <div class="epic-row-side">
        <div class="epic-row-version">spec v${escapeHtml(item.current_spec_version || 1)} · plan v${escapeHtml(item.plan_version || 0)}</div>
        ${progressMarkup(item.progress)}
      </div>
    </a>`).join("")}</div>`;
}

export function renderEpics(payload, route) {
  const filters = payload.filters || {};
  const project = filters.project_key || route.project || null;
  const status = filters.status || route.status || "";
  const params = { project, status };
  return `
    <div class="page-toolbar">
      <div><div class="section-eyebrow">EPIC WORKSPACE</div><div class="section-heading">Крупные инициативы</div></div>
      <div class="toolbar-controls">${projectPicker(payload.projects || [], project, "epics", { status })}</div>
    </div>
    <section class="panel">
      <div class="panel-header panel-header-wrap">
        <div><div class="panel-title">Эпики</div><div class="panel-hint">Спецификация, Phase 0, последовательные Tasks и full-Epic review</div></div>
        ${filterTabs([
          { label: "Все", value: "" },
          { label: "Открытые", value: "open" },
          { label: "В работе", value: "running" },
          { label: "Blocked", value: "blocked" },
          { label: "Завершённые", value: "completed" },
          { label: "Архив", value: "archived" },
        ], status, "epics", { project }, "status")}
      </div>
      ${epicRows(payload.items || [])}
      <div class="panel-footer">
        <span class="muted">${escapeHtml(payload.pagination?.total || 0)} всего</span>
        ${pagination(payload.pagination, "epics", params)}
      </div>
    </section>`;
}

export function renderEpicList(payload, projectKey) {
  const items = payload?.epics || [];
  const visible = items.slice(0, 5);
  return `<section class="panel panel-accent">
    <div class="panel-header">
      <div><div class="panel-title">Эпики</div><div class="panel-hint">Крупные инициативы этого проекта</div></div>
      <a class="panel-header-link" href="${hashUrl("epics", { project: projectKey })}">Все эпики →</a>
    </div>
    ${visible.length ? epicRows(visible.map((item) => ({ ...item, project: { key: projectKey, name: "Проект" } }))) : `<div class="empty">Epics ещё не созданы</div>`}
  </section>`;
}

function epicTabs(projectKey, epicKey, active) {
  const tabs = [
    ["overview", "Обзор"],
    ["specification", "Specification"],
    ["tasks", "Tasks"],
    ["audits", "Audits"],
  ];
  return `<nav class="epic-tabs" aria-label="Разделы Epic">${tabs.map(([mode, label]) => `<a class="epic-tab ${active === mode ? "active" : ""}" href="${hashUrl(`epic/${encodeURIComponent(projectKey)}/${encodeURIComponent(epicKey)}`, { mode: mode === "overview" ? null : mode })}">${escapeHtml(label)}</a>`).join("")}</nav>`;
}

function overviewMode(epic, projectKey) {
  const quality = epic.spec_quality || {};
  return `<div class="dashboard-grid">
    <div class="dashboard-main">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Task plan</div><div class="panel-hint">Фактический прогресс по последовательному execution plan</div></div><span class="muted">${escapeHtml((epic.plan || []).length)} пунктов</span></div>
        ${plan(epic.plan || [], projectKey)}
      </section>
    </div>
    <div class="dashboard-side">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Состояние Epic</div><div class="panel-hint">Durable версии и execution boundary</div></div></div>
        <div class="info-list epic-state-grid">
          ${infoRow("Статус", epic.status || "draft")}
          ${infoRow("Approved spec", epic.approved_spec_version ? `v${epic.approved_spec_version}` : "—")}
          ${infoRow("Execution spec", epic.execution_spec_version ? `v${epic.execution_spec_version}` : "—")}
          ${infoRow("Plan version", `v${epic.plan_version || 0}`)}
          ${infoRow("Создан", epic.created_at ? age(epic.created_at) : "—")}
          ${infoRow("Обновлён", epic.updated_at ? age(epic.updated_at) : "—")}
        </div>
        <div class="epic-spec-quality"><strong>Spec quality:</strong> ${quality.ready_for_human_review ? "готова к human review" : `${escapeHtml((quality.missing_recommended_sections || []).length)} секций требуют внимания`}</div>
      </section>
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Последние аудиты</div><div class="panel-hint">Краткий срез без перегруза</div></div></div>
        ${audits(epic.audits || [], { compact: true })}
      </section>
    </div>
  </div>`;
}

function specificationMode(epic) {
  const spec = epic.spec || {};
  const versions = epic.spec_versions || [];
  const visibleVersions = versions.slice(-10).reverse();
  return `<div class="dashboard-grid">
    <div class="dashboard-main">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Specification v${escapeHtml(spec.version || epic.current_spec_version || 1)}</div><div class="panel-hint">Человекочитаемый durable product contract</div></div><span class="muted">${escapeHtml(spec.created_at ? age(spec.created_at) : "")}</span></div>
        <article class="epic-spec">${markdown(spec.content || "")}</article>
      </section>
    </div>
    <div class="dashboard-side">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Spec history</div><div class="panel-hint">Последние 10 immutable revisions</div></div></div>
        <div class="stage-list">${visibleVersions.map((item) => `<div class="stage-row"><div class="stage-index">v${escapeHtml(item.version)}</div><div class="stage-body"><div class="stage-title">${escapeHtml(item.source || "revision")}</div><div class="stage-summary">${escapeHtml(item.change_summary || "—")}</div><div class="stage-foot">${escapeHtml(item.rationale || "")}</div></div></div>`).join("") || `<div class="empty">Нет истории версий</div>`}${versions.length > 10 ? `<div class="table-caption">Показаны 10 последних из ${escapeHtml(versions.length)} версий</div>` : ""}</div>
      </section>
    </div>
  </div>`;
}

export function renderEpicDetail(payload, route = {}) {
  const epic = payload?.epic || {};
  const projectKey = payload?.project_key || route.projectKey || "";
  const mode = ["specification", "tasks", "audits"].includes(route.mode) ? route.mode : "overview";
  let content = overviewMode(epic, projectKey);
  if (mode === "specification") content = specificationMode(epic);
  if (mode === "tasks") content = `<section class="panel"><div class="panel-header"><div><div class="panel-title">Task plan</div><div class="panel-hint">Phase 0 → STANDARD work Tasks → final docs/knowledge/full review</div></div></div>${plan(epic.plan || [], projectKey)}</section>`;
  if (mode === "audits") content = `<section class="panel"><div class="panel-header"><div><div class="panel-title">Audits</div><div class="panel-hint">Последние 10 аудитов точной версии specification</div></div><span class="muted">${escapeHtml((epic.audits || []).length)} всего</span></div>${audits(epic.audits || [])}</section>`;
  return `
    <div class="detail-hero compact-hero">
      <div>
        <a class="back-link" href="${hashUrl("epics", { project: projectKey })}">← Все эпики</a>
        <div class="detail-kicker">${escapeHtml(epic.key || "Epic")}</div>
        <h2>${escapeHtml(epic.title || "")}</h2>
        <div class="detail-subtitle">approved v${escapeHtml(epic.approved_spec_version || "—")} · execution v${escapeHtml(epic.execution_spec_version || "—")} · plan v${escapeHtml(epic.plan_version || 0)}</div>
      </div>
      ${stateBadge(epic.status || "draft")}
    </div>
    ${epic.blocked_reason ? `<div class="notice warning">${escapeHtml(epic.blocked_reason)}</div>` : ""}
    ${epicTabs(projectKey, epic.key || "", mode)}
    ${content}`;
}
