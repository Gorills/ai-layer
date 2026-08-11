import { age, escapeHtml } from "../format.js";
import { stateBadge } from "../components/common.js";

function inline(text) {
  return escapeHtml(text || "")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function markdown(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let list = null;
  let code = false;
  const closeList = () => {
    if (!list) return;
    out.push(`</${list}>`);
    list = null;
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().startsWith("```")) {
      closeList();
      code = !code;
      out.push(code ? "<pre class=\"epic-code\"><code>" : "</code></pre>");
      continue;
    }
    if (code) {
      out.push(`${escapeHtml(raw)}\n`);
      continue;
    }
    if (!line.trim()) {
      closeList();
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(5, heading[1].length + 1);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (list !== "ul") { closeList(); list = "ul"; out.push("<ul>"); }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      if (list !== "ol") { closeList(); list = "ol"; out.push("<ol>"); }
      out.push(`<li>${inline(ordered[1])}</li>`);
      continue;
    }
    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  if (code) out.push("</code></pre>");
  return out.join("");
}

function plan(items) {
  if (!items?.length) return `<div class="empty">Task plan появится после Phase 0</div>`;
  return `<div class="stage-list">${items.map((item) => `
    <div class="stage-row ${escapeHtml(item.status || "")}">
      <div class="stage-index">${escapeHtml(item.ordinal)}</div>
      <div class="stage-body">
        <div class="stage-title">${escapeHtml(item.title || item.key)}</div>
        <div class="stage-summary">${escapeHtml(item.goal || "—")}</div>
        <div class="stage-foot">${escapeHtml(item.kind)} · spec v${escapeHtml(item.spec_version)}${item.task_key ? ` · ${escapeHtml(item.task_key)} · ${escapeHtml(item.task_status || "—")}` : ""}</div>
      </div>
      ${stateBadge(item.status || "pending")}
    </div>`).join("")}</div>`;
}

function audits(items) {
  if (!items?.length) return `<div class="empty">Аудитов пока нет</div>`;
  return `<div class="finding-list">${[...items].reverse().map((item) => `
    <div class="finding">
      <div class="finding-head"><strong>spec v${escapeHtml(item.spec_version)}</strong><span>${escapeHtml(item.scope || "independent")}</span></div>
      <div class="finding-problem">${escapeHtml(item.summary)}</div>
      <div class="finding-path">${escapeHtml(item.created_at ? age(item.created_at) : "")}${item.auditor_id ? ` · ${escapeHtml(item.auditor_id)}` : ""}</div>
      ${(item.findings || []).map((finding) => `<div class="finding-fix"><strong>${escapeHtml(finding.severity || "finding")}</strong> · ${escapeHtml(finding.problem || finding.summary || JSON.stringify(finding))}</div>`).join("")}
    </div>`).join("")}</div>`;
}

export function renderEpicList(payload, projectKey) {
  const items = payload?.epics || [];
  return `<section class="panel panel-accent">
    <div class="panel-header">
      <div><div class="panel-title">Epics</div><div class="panel-hint">Спеки, Phase 0, последовательные Tasks и финальный full-Epic review</div></div>
      <span class="muted">${escapeHtml(items.length)} всего</span>
    </div>
    ${items.length ? `<div class="stage-list">${items.map((item) => `
      <a class="stage-row ${escapeHtml(item.status || "")}" href="#/epic/${encodeURIComponent(projectKey)}/${encodeURIComponent(item.key)}" style="text-decoration:none;color:inherit">
        <div class="stage-index">${escapeHtml(item.key)}</div>
        <div class="stage-body">
          <div class="stage-title">${escapeHtml(item.title)}</div>
          <div class="stage-summary">spec v${escapeHtml(item.current_spec_version)}${item.execution_spec_version ? ` · execution v${escapeHtml(item.execution_spec_version)}` : ""} · plan v${escapeHtml(item.plan_version || 0)}</div>
          <div class="stage-foot">${escapeHtml(item.updated_at ? age(item.updated_at) : "")}${item.blocked_reason ? ` · ${escapeHtml(item.blocked_reason)}` : ""}</div>
        </div>
        ${stateBadge(item.status || "draft")}
      </a>`).join("")}</div>` : `<div class="empty">Epics ещё не созданы</div>`}
  </section>`;
}

export function renderEpicDetail(payload) {
  const epic = payload?.epic || {};
  const spec = epic.spec || {};
  const versions = epic.spec_versions || [];
  const quality = epic.spec_quality || {};
  return `
    <div class="project-head">
      <div><h2>${escapeHtml(epic.key || "Epic")} · ${escapeHtml(epic.title || "")}</h2><div class="path">approved v${escapeHtml(epic.approved_spec_version || "—")} · execution v${escapeHtml(epic.execution_spec_version || "—")}</div></div>
      ${stateBadge(epic.status || "draft")}
    </div>
    ${epic.blocked_reason ? `<div class="alert">${escapeHtml(epic.blocked_reason)}</div>` : ""}
    <div class="summary-grid">
      <div class="metric"><div class="metric-label">Текущая спека</div><div class="metric-value">v${escapeHtml(epic.current_spec_version || 1)}</div><div class="metric-note">${escapeHtml(spec.source || "draft")}</div></div>
      <div class="metric"><div class="metric-label">Аудиты</div><div class="metric-value">${escapeHtml((epic.audits || []).length)}</div><div class="metric-note">неограниченная история</div></div>
      <div class="metric"><div class="metric-label">Task plan</div><div class="metric-value">${escapeHtml((epic.plan || []).length)}</div><div class="metric-note">plan v${escapeHtml(epic.plan_version || 0)}</div></div>
      <div class="metric"><div class="metric-label">Spec quality</div><div class="metric-value">${quality.ready_for_human_review ? "ready" : "needs sections"}</div><div class="metric-note">${escapeHtml((quality.completeness_warnings || []).length)} completeness warning(s)</div></div>
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Specification v${escapeHtml(spec.version || epic.current_spec_version || 1)}</div><div class="panel-hint">Человекочитаемый durable contract; source остаётся авторитетом для Phase 0</div></div><span class="muted">${escapeHtml(spec.created_at ? age(spec.created_at) : "")}</span></div>
          <article class="epic-spec">${markdown(spec.content || "")}</article>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Task plan</div><div class="panel-hint">Phase 0 → STANDARD work Tasks → final docs/knowledge/full review</div></div></div>
          ${plan(epic.plan || [])}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Audits</div><div class="panel-hint">Каждый аудит привязан к точной версии спеки</div></div></div>
          ${audits(epic.audits || [])}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Spec history</div><div class="panel-hint">Approved baseline никогда не переписывается молча</div></div></div>
          <div class="stage-list">${versions.map((item) => `<div class="stage-row"><div class="stage-index">v${escapeHtml(item.version)}</div><div class="stage-body"><div class="stage-title">${escapeHtml(item.source || "revision")}</div><div class="stage-summary">${escapeHtml(item.change_summary || "—")}</div><div class="stage-foot">${escapeHtml(item.rationale || "")}</div></div></div>`).join("") || `<div class="empty">Нет истории версий</div>`}</div>
        </section>
      </div>
    </div>`;
}
