import { age, escapeHtml } from "../format.js";
import { metric, stateBadge } from "../components/common.js";
import { compactList, filterTabs, hashUrl, infoRow, pagination, projectPicker } from "../components/ui.js";

const WORK_STATUSES = [
  { label: "Все", value: "" },
  { label: "Активные", value: "active" },
  { label: "Blocked", value: "blocked" },
  { label: "Завершённые", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Interrupted", value: "interrupted" },
  { label: "Abandoned", value: "abandoned" },
];

export function workHref(projectKey, workKey) {
  if (!projectKey || !workKey) return "#/work";
  return hashUrl(`work/${encodeURIComponent(projectKey)}/${encodeURIComponent(workKey)}`);
}

export function workDisplayState(work) {
  if (work?.live) return work.status || "active";
  if (work?.status === "active") return "stale";
  return work?.status || "idle";
}

export function workAttentionReason(work) {
  if (work?.status === "blocked") return "blocked";
  if (work?.status === "active" && !work.live) return "stale";
  const mapStatus = (work?.map_disposition || {}).status;
  if (mapStatus === "pending" || mapStatus === "deferred") return `map ${mapStatus}`;
  if (work?.map_pending) return "map pending";
  return work?.status || "attention";
}

function workTimestamp(work, preferred) {
  return Date.parse(work?.[preferred] || work?.updated_at || work?.last_milestone_at || 0) || 0;
}

export function primaryProjectWork(project) {
  const work = project?.work || {};
  const live = (work.live || []).find((item) => item.live);
  if (live) return live;
  const openAttention = (work.attention || []).find(
    (item) => item.status === "active" || item.status === "blocked",
  );
  return openAttention || (work.recent || [])[0] || null;
}

export function collectPortfolioWork(projects, { nowLimit = 6, attentionLimit = 8, recentLimit = 8 } = {}) {
  const now = [];
  const attention = [];
  const recent = [];
  for (const project of projects || []) {
    const bucket = project.work || {};
    for (const item of bucket.live || []) {
      if (item.live) now.push({ project, work: item });
    }
    for (const item of bucket.attention || []) attention.push({ project, work: item });
    for (const item of bucket.recent || []) recent.push({ project, work: item });
  }
  now.sort((left, right) => workTimestamp(right.work, "updated_at") - workTimestamp(left.work, "updated_at"));
  attention.sort((left, right) => workTimestamp(right.work, "updated_at") - workTimestamp(left.work, "updated_at"));
  recent.sort((left, right) => workTimestamp(right.work, "completed_at") - workTimestamp(left.work, "completed_at"));
  return {
    now: now.slice(0, nowLimit),
    attention: attention.slice(0, attentionLimit),
    recent: recent.slice(0, recentLimit),
    nowTotal: now.length,
    attentionTotal: attention.length,
    recentTotal: recent.length,
  };
}

export function workRow({ project, work }, { reason = "" } = {}) {
  const card = work.project || {};
  const projectKey = project?.key || card.key;
  const projectName = project?.name || card.name || "Проект";
  return `<a class="record-row" href="${workHref(projectKey, work.key)}">
    <div class="record-primary">
      <div class="record-kicker">${escapeHtml(projectName)} · ${escapeHtml(work.key || "Work")}${reason ? ` · ${escapeHtml(reason)}` : ""}</div>
      <div class="record-title">${escapeHtml(work.goal || "—")}</div>
      <div class="record-meta">${escapeHtml(work.kind || "work")} · ${escapeHtml(work.observability_coverage || "unknown coverage")}${work.live ? " · live" : ""}</div>
    </div>
    <div class="record-side">
      ${stateBadge(workDisplayState(work))}
      <span class="record-time">${escapeHtml(work.updated_at ? age(work.updated_at) : "")}</span>
    </div>
  </a>`;
}

export function workStack(items, emptyLabel, reasonFor, totals = null) {
  if (!items?.length) return `<div class="empty">${escapeHtml(emptyLabel)}</div>`;
  const shown = items.length;
  const total = Number(totals?.total || shown);
  const caption = total > shown
    ? `<div class="table-caption">Показаны ${escapeHtml(shown)} из ${escapeHtml(total)}</div>`
    : "";
  return `<div class="record-list">${items.map((item) => workRow(item, { reason: reasonFor ? reasonFor(item.work) : "" })).join("")}</div>${caption}`;
}

function workRows(items) {
  if (!items?.length) return `<div class="empty">WorkItems по выбранному фильтру нет</div>`;
  return `<div class="record-list">${items.map((work) => workRow({ project: work.project || {}, work })).join("")}</div>`;
}

export function renderWorkList(payload, route) {
  const filters = payload.filters || {};
  const project = filters.project_key || route.project || null;
  const status = filters.status || route.status || "";
  const params = { project, status };
  return `
    <div class="page-toolbar">
      <div>
        <div class="section-eyebrow">WORK</div>
        <div class="section-heading">Обычная пользовательская работа</div>
      </div>
      <div class="toolbar-controls">${projectPicker(payload.projects || [], project, "work", { status })}</div>
    </div>
    <section class="panel">
      <div class="panel-header panel-header-wrap">
        <div><div class="panel-title">WorkItems</div><div class="panel-hint">Не Managed Task и не MCP bridge. live требует не-stale AgentRun.</div></div>
        ${filterTabs(WORK_STATUSES, status, "work", { project }, "status")}
      </div>
      ${workRows(payload.items || [])}
      <div class="panel-footer">
        <span class="muted">${escapeHtml(payload.pagination?.total || 0)} всего</span>
        ${pagination(payload.pagination, "work", params)}
      </div>
    </section>`;
}

function pathList(paths, emptyLabel) {
  return compactList((paths || []).slice(0, 20), emptyLabel);
}

function checks(items) {
  const visible = (items || []).slice(0, 10);
  if (!visible.length) return `<div class="empty">Проверок нет</div>`;
  return `<div class="verification-list">${visible.map((item) => `
    <div class="verification-row">
      <div class="verification-main">
        <div class="verification-command">${escapeHtml(item.name || "check")}</div>
        <div class="verification-meta">${escapeHtml(item.status || "—")}${item.summary ? ` · ${escapeHtml(item.summary)}` : ""}</div>
      </div>
      ${stateBadge(item.status === "passed" ? "completed" : item.status || "pending")}
    </div>`).join("")}${(items || []).length > 10 ? `<div class="table-caption">Показаны 10 из ${escapeHtml(items.length)}</div>` : ""}</div>`;
}

function runRows(runs, emptyLabel) {
  if (!runs?.length) return `<div class="empty">${escapeHtml(emptyLabel)}</div>`;
  return `<div class="stage-list">${runs.map((run) => `
    <div class="stage-row ${escapeHtml(run.stale ? "stale" : run.status || "")}">
      <div class="stage-index">${escapeHtml((run.role || "run").slice(0, 1).toUpperCase())}</div>
      <div class="stage-body">
        <div class="stage-title">${escapeHtml(run.role || "run")} · ${escapeHtml(run.host || "—")} / ${escapeHtml(run.client || "—")}</div>
        <div class="stage-summary">${escapeHtml(run.last_meaningful_action || "нет last meaningful action")}</div>
        <div class="stage-foot">${escapeHtml(run.observability_coverage || "unknown")} · ${escapeHtml(run.assurance || "—")} · heartbeat ${escapeHtml(run.heartbeat_at ? age(run.heartbeat_at) : "—")}${run.session_id ? ` · session ${escapeHtml(String(run.session_id).slice(0, 12))}` : ""}</div>
      </div>
      ${stateBadge(run.stale ? "stale" : run.effective_status || run.status || "idle")}
    </div>`).join("")}</div>`;
}

function timeline(items, truncated, total) {
  if (!items?.length) return `<div class="empty">Событий работы нет</div>`;
  return `<div class="activity-list">${items.map((item) => {
    const payload = item.payload || {};
    const summary = payload.summary || payload.reason || payload.goal || payload.status || "";
    return `<div class="activity-row">
      <div class="activity-status ${escapeHtml(payload.status || item.importance || "")}"></div>
      <div class="activity-time">${escapeHtml(item.occurred_at ? age(item.occurred_at) : "—")}</div>
      <div class="activity-main">
        <div class="activity-title">${escapeHtml(item.event_type || "event")}</div>
        <div class="activity-meta">${escapeHtml(item.actor_kind || item.actor_id || "system")}${summary ? ` · ${escapeHtml(summary)}` : ""}${item.assurance ? ` · ${escapeHtml(item.assurance)}` : ""}</div>
      </div>
    </div>`;
  }).join("")}</div>${truncated ? `<div class="table-caption">Показаны ${escapeHtml(items.length)} из ${escapeHtml(total)} событий</div>` : ""}`;
}

export function renderWorkDetail(payload) {
  const work = payload.work || {};
  const project = payload.project || {};
  const runs = work.runs || [];
  const rootRuns = runs.filter((run) => run.role === "root");
  const subRuns = runs.filter((run) => run.role === "subagent");
  const map = work.map_disposition || {};
  const delta = work.repository_delta || {};
  const staleActive = work.status === "active" && !work.live;
  return `
    <div class="detail-hero">
      <div>
        <a class="back-link" href="${hashUrl("work", { project: project.key })}">← Все WorkItems</a>
        <div class="detail-kicker">${escapeHtml(project.name || "Проект")} · ${escapeHtml(work.key || "Work")}</div>
        <h2>${escapeHtml(work.goal || "—")}</h2>
        <div class="detail-subtitle">${escapeHtml(work.kind || "work")} · ${escapeHtml(work.observability_coverage || "unknown coverage")} · ${escapeHtml(work.assurance || "—")}</div>
      </div>
      ${stateBadge(workDisplayState(work))}
    </div>
    ${staleActive ? `<div class="notice warning"><strong>Нет живого AgentRun.</strong> Активный WorkItem устарел по heartbeat — resume или завершите его. Это не live ordinary work.</div>` : ""}
    ${work.status === "blocked" ? `<div class="notice warning"><strong>Work заблокирован.</strong> ${escapeHtml(work.result_summary || "Нужно внимание")}</div>` : ""}
    <div class="summary-grid">
      ${metric("Статус", workDisplayState(work), work.live ? "non-stale AgentRun" : "не live")}
      ${metric("Project Map", map.status || (work.map_pending ? "pending" : "—"), map.reason || "")}
      ${metric("Checks", (work.checks || []).length, work.result_summary || "bounded summaries")}
      ${metric("Изменения", delta.changed_files ?? (work.changed_paths || []).length, delta.assurance || work.assurance || "")}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Хронология</div><div class="panel-hint">Собственные события и linked Task/Epic milestones без внутренней истории</div></div><span class="muted">${escapeHtml(payload.timeline_total ?? (payload.timeline || []).length)}</span></div>
          ${timeline(payload.timeline || [], payload.timeline_truncated, payload.timeline_total)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Root runs</div><div class="panel-hint">Heartbeat и staleness отдельно от MCP bridges</div></div><span class="muted">${escapeHtml(rootRuns.length)}</span></div>
          ${runRows(rootRuns, "Root AgentRun нет")}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Subagent runs</div><div class="panel-hint">Дочерние runs не доказывают live ordinary work сами по себе</div></div><span class="muted">${escapeHtml(subRuns.length)}</span></div>
          ${runRows(subRuns, "Subagent runs нет")}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Checks</div><div class="panel-hint">Только имя/статус/краткое summary</div></div></div>
          ${checks(work.checks || [])}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Связи</div><div class="panel-hint">Managed Task/Epic — отдельные read models</div></div></div>
          <div class="info-list">
            ${infoRow("Проект", project.name || project.key || "—")}
            ${infoRow("Linked Task", work.linked_task_key || "нет", work.linked_task_id || "")}
            ${infoRow("Linked Epic", work.linked_epic_key || "нет", work.linked_epic_id || "")}
            ${infoRow("Начато", work.started_at ? age(work.started_at) : "—")}
            ${infoRow("Обновлено", work.updated_at ? age(work.updated_at) : "—")}
            ${infoRow("Завершено", work.completed_at ? age(work.completed_at) : "—")}
          </div>
          ${work.linked_task_key && project.key ? `<a class="panel-link" href="#/task/${encodeURIComponent(project.key)}/${encodeURIComponent(work.linked_task_key)}">Открыть Task →</a>` : ""}
          ${work.linked_epic_key && project.key ? `<a class="panel-link" href="#/epic/${encodeURIComponent(project.key)}/${encodeURIComponent(work.linked_epic_key)}">Открыть Epic →</a>` : ""}
          ${work.id ? `<a class="panel-link" href="${hashUrl("activity", { project: project.key, work_id: work.id })}">События этой работы →</a>` : ""}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Project Map</div><div class="panel-hint">pending/deferred остаются attention, не healthy completion</div></div>${stateBadge(map.status || (work.map_pending ? "pending" : "none"))}</div>
          <div class="info-list">
            ${infoRow("Disposition", map.status || "—", map.reason || "")}
            ${infoRow("Evidence event", map.event_id || "—")}
          </div>
          ${pathList(map.scope || [], "Scope не указан")}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Repository delta</div><div class="panel-hint">Метаданные без source bodies</div></div></div>
          <div class="info-list">
            ${infoRow("Base", delta.base_revision || "—")}
            ${infoRow("Final", delta.final_revision || "—")}
            ${infoRow("Files", delta.changed_files ?? "—")}
            ${infoRow("Insertions / deletions", `${delta.insertions ?? "—"} / ${delta.deletions ?? "—"}`)}
            ${infoRow("Dirty", delta.dirty == null ? "—" : String(delta.dirty))}
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Пути</div><div class="panel-hint">До 20 project-relative путей</div></div></div>
          <div class="content-block"><h3>Reviewed</h3>${pathList(work.reviewed_paths, "Нет")}</div>
          <div class="content-block"><h3>Changed</h3>${pathList(work.changed_paths, "Нет")}</div>
          ${work.result_summary ? `<div class="content-block"><h3>Result</h3><p>${escapeHtml(work.result_summary)}</p></div>` : ""}
        </section>
      </div>
    </div>`;
}
