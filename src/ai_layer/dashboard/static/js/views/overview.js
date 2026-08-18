import { age, escapeHtml } from "../format.js";
import { metric, scanLabel, stateBadge } from "../components/common.js";
import { collectPortfolioWork, primaryProjectWork, workAttentionReason, workHref } from "./work.js";

function mapLabel(project) {
  const map = project.project_map || {};
  const current = Number(map.semantic_current || 0);
  const missing = Number(map.semantic_missing || 0);
  const stale = Number(map.semantic_stale || 0);
  const total = current + missing + stale;
  if (!total) return "карта не построена";
  const coverage = Math.round(Number(map.semantic_current_coverage || 0) * 100);
  return `${coverage}% · ${current}/${total} current`;
}

function projectAttention(project) {
  const items = [];
  for (const work of project.work?.attention || []) {
    items.push({
      project,
      title: work.goal || work.key || "Работа",
      detail: `${work.key || "Work"} · ${workAttentionReason(work)}`,
      state: work.status === "active" && !work.live ? "stale" : work.status || "attention",
      href: workHref(project.key, work.key),
    });
  }
  const task = project.task || {};
  if (task.human_attention_required) {
    items.push({
      project,
      title: task.goal || `${task.key || "Task"} требует решения`,
      detail: task.human_attention_reason || `${task.key || "Task"} · нужен ответ пользователя`,
      state: "attention",
      href: `#/task/${encodeURIComponent(project.key)}/${encodeURIComponent(task.key)}`,
    });
  }
  const protocol = project.protocol_state || {};
  if (protocol.status === "warning") {
    items.push({
      project,
      title: "Protocol требует проверки",
      detail: `${protocol.failures_5m || 0} failures за 5 минут`,
      state: "warning",
      href: `#/monitoring?project=${encodeURIComponent(project.key)}`,
    });
  }
  const map = project.project_map || {};
  const stale = Number(map.semantic_stale || 0);
  const missing = Number(map.semantic_missing || 0);
  if (stale || missing) {
    items.push({
      project,
      title: "Project Map требует обновления",
      detail: `${stale} stale · ${missing} missing`,
      state: "stale",
      href: `#/project/${encodeURIComponent(project.key)}/knowledge`,
    });
  }
  return items;
}

function projectAttentionCount(project) {
  return projectAttention(project).length;
}

function projectCard(project) {
  const work = primaryProjectWork(project);
  const recent = (project.work?.recent || [])[0] || null;
  const attention = projectAttentionCount(project);
  const task = project.task || null;
  const href = `#/project/${encodeURIComponent(project.key)}`;
  const state = attention ? "attention" : project.project_state || "healthy";
  return `<a class="portfolio-project-card" href="${href}">
    <div class="portfolio-project-head">
      <div><div class="portfolio-project-name">${escapeHtml(project.name)}</div><div class="portfolio-project-root">${escapeHtml(project.root || "")}</div></div>
      ${stateBadge(state)}
    </div>
    <div class="portfolio-project-focus">
      <span class="portfolio-label">${work && ["active", "blocked"].includes(work.status) ? "Сейчас" : "Последняя работа"}</span>
      <strong>${escapeHtml(work?.goal || "Активной работы нет")}</strong>
      <span>${work ? `${escapeHtml(work.key || "Work")} · ${escapeHtml(work.status || "—")}` : "Проект готов к следующей задаче"}</span>
    </div>
    <div class="portfolio-project-facts">
      <span><strong>${escapeHtml(attention)}</strong> attention</span>
      <span><strong>${escapeHtml(task?.status || "—")}</strong> task</span>
      <span><strong>${escapeHtml(mapLabel(project))}</strong></span>
    </div>
    ${recent ? `<div class="portfolio-project-recent"><span>Последний результат</span><strong>${escapeHtml(recent.result_summary || recent.goal || "Завершено")}</strong><em>${escapeHtml(recent.completed_at ? age(recent.completed_at) : recent.updated_at ? age(recent.updated_at) : "")}</em></div>` : ""}
    <div class="portfolio-project-foot"><span>scan ${escapeHtml(scanLabel(project.last_scan))}</span><span>Открыть проект →</span></div>
  </a>`;
}

function projectGrid(projects) {
  const visible = (projects || []).slice(0, 10);
  if (!visible.length) return `<div class="empty">Зарегистрированных проектов нет</div>`;
  return `<div class="portfolio-project-grid">${visible.map(projectCard).join("")}</div>${projects.length > visible.length ? `<div class="table-caption">Показаны ${escapeHtml(visible.length)} из ${escapeHtml(projects.length)} проектов</div>` : ""}`;
}

function attentionList(items) {
  if (!items?.length) return `<div class="calm-state large"><strong>Ничего не требует вмешательства</strong><span>Нет blocked/stale работы, решений пользователя, protocol warnings или stale Project Map.</span></div>`;
  return `<div class="attention-work-list">${items.map((item) => `<a class="attention-work-row" href="${item.href}">
    <div class="attention-work-project">${escapeHtml(item.project.name)}</div>
    <div class="attention-work-main"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></div>
    ${stateBadge(item.state)}
  </a>`).join("")}</div>`;
}

function activeList(items) {
  if (!items?.length) return `<div class="empty">Сейчас нет наблюдаемой active work</div>`;
  return `<div class="active-work-grid">${items.map(({ project, work }) => `<a class="active-work-card" href="${workHref(project.key, work.key)}">
    <div class="record-kicker">${escapeHtml(project.name)} · ${escapeHtml(work.key || "Work")}</div>
    <strong>${escapeHtml(work.goal || "—")}</strong>
    <span>${escapeHtml((work.runs || []).find((run) => run.role === "root" && !run.stale)?.last_meaningful_action || "Выполняется host-natively")}</span>
    <div class="active-work-foot">${stateBadge("active")}<em>${escapeHtml(work.updated_at ? age(work.updated_at) : "")}</em></div>
  </a>`).join("")}</div>`;
}

function recentList(items) {
  if (!items?.length) return `<div class="empty">Недавних завершённых WorkItems нет</div>`;
  return `<div class="recent-result-list">${items.map(({ project, work }) => {
    const changed = work.repository_delta?.changed_files ?? (work.changed_paths || []).length;
    const checks = (work.checks || []).length;
    return `<a class="recent-result-row" href="${workHref(project.key, work.key)}">
      <div class="recent-result-project">${escapeHtml(project.name)}</div>
      <div class="recent-result-main"><strong>${escapeHtml(work.result_summary || work.goal || "Завершено")}</strong><span>${escapeHtml(work.key || "Work")} · ${escapeHtml(changed)} files · ${escapeHtml(checks)} checks</span></div>
      <span class="record-time">${escapeHtml(work.completed_at ? age(work.completed_at) : work.updated_at ? age(work.updated_at) : "")}</span>
    </a>`;
  }).join("")}</div>`;
}

function systemStrip(data) {
  const db = data.database || {};
  const core = data.core_runtime || {};
  const summary = data.summary || {};
  const healthy = Boolean(db.connected) && core.status !== "degraded";
  return `<section class="system-strip">
    <div class="system-strip-main"><span class="status-dot ${healthy ? "online" : "offline"}"></span><div><strong>${healthy ? "Runtime в норме" : "Runtime требует проверки"}</strong><span>Технические детали не мешают обзору проектов</span></div></div>
    <div class="system-strip-facts"><span>PostgreSQL <strong>${db.connected ? "ready" : "down"}</strong></span><span>MCP <strong>${escapeHtml(summary.active_mcp_bridges ?? 0)} active</strong></span><span>Warnings <strong>${escapeHtml(summary.protocol_warnings ?? 0)}</strong></span></div>
    <a href="#/monitoring">Мониторинг →</a>
  </section>`;
}

export function renderOverview(data) {
  const summary = data.summary || {};
  const projects = data.projects || [];
  const portfolio = collectPortfolioWork(projects, { nowLimit: 6, attentionLimit: 8, recentLimit: 8 });
  const attention = projects.flatMap(projectAttention);
  const attentionTotal = attention.length;
  const firstActive = (portfolio.now || [])[0] || null;
  const focusTitle = firstActive ? `${firstActive.work.key || "Work"} · ${firstActive.work.goal || "Текущая работа"}` : "Нет активной работы";
  const sortedProjects = [...projects].sort((left, right) => {
    const leftAttention = projectAttentionCount(left);
    const rightAttention = projectAttentionCount(right);
    if (leftAttention !== rightAttention) return rightAttention - leftAttention;
    const leftLive = (left.work?.live || []).some((item) => item.live) ? 1 : 0;
    const rightLive = (right.work?.live || []).some((item) => item.live) ? 1 : 0;
    if (leftLive !== rightLive) return rightLive - leftLive;
    return String(left.name || "").localeCompare(String(right.name || ""));
  });
  return `
    ${!data.database?.connected ? `<div class="notice danger">PostgreSQL недоступен. Durable Work/Task данные могут быть неполными.</div>` : ""}
    <section class="portfolio-hero">
      <div>
        <div class="section-eyebrow">LOCAL PORTFOLIO</div>
        <h2>${attentionTotal ? `${attentionTotal} ${attentionTotal === 1 ? "сигнал требует" : "сигналов требуют"} внимания` : portfolio.nowTotal ? `${portfolio.nowTotal} ${portfolio.nowTotal === 1 ? "работа идёт" : "работы идут"} сейчас` : "Рабочее пространство спокойно"}</h2>
        <div class="focus-title">${escapeHtml(focusTitle)}</div>
        <p>${attentionTotal ? "Сначала разберите actionable сигналы. Остальная информация остаётся ниже по приоритету." : "Откройте проект один раз — внутри будут текущая работа, результаты, знания и история без повторного выбора контекста."}</p>
      </div>
      <div class="portfolio-hero-count">${escapeHtml(projects.length)}<span>проектов</span></div>
    </section>
    <div class="summary-grid overview-summary-grid">
      ${metric("Сейчас в работе", summary.active_work ?? portfolio.nowTotal ?? 0, "только live Work")}
      ${metric("Нужно внимание", attentionTotal, "work · task · map · protocol")}
      ${metric("Недавно завершено", portfolio.recentTotal ?? summary.recent_work ?? 0, "terminal Work")}
      ${metric("System warnings", summary.protocol_warnings ?? 0, `${summary.failures_5m ?? 0} failures / 5m`)}
    </div>
    <section class="panel priority-panel ${attentionTotal ? "has-attention" : ""}">
      <div class="panel-header"><div><div class="panel-title">Сначала внимание</div><div class="panel-hint">Проблемы, для которых действительно нужно действие человека или продолжение работы</div></div><a class="panel-header-link" href="#/work">Все →</a></div>
      ${attentionList(attention.slice(0, 8))}
    </section>
    <div class="portfolio-two-column">
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Сейчас выполняется</div><div class="panel-hint">Только live WorkItems, а не открытые Task или MCP соединения</div></div></div>
        ${activeList(portfolio.now)}
      </section>
      <section class="panel">
        <div class="panel-header"><div><div class="panel-title">Последние результаты</div><div class="panel-hint">Что реально было завершено по проектам</div></div></div>
        ${recentList(portfolio.recent)}
      </section>
    </div>
    <section class="panel projects-panel">
      <div class="panel-header"><div><div class="panel-title">Проекты</div><div class="panel-hint">Каждая карточка — вход в единое рабочее пространство проекта</div></div><span class="muted">${escapeHtml(projects.length)} всего</span></div>
      ${projectGrid(sortedProjects)}
    </section>
    ${systemStrip(data)}`;
}
