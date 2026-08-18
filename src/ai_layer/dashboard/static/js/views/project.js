import { age, escapeHtml } from "../format.js";
import { agentsList, metric, stageName, stateBadge } from "../components/common.js";
import { hashUrl, infoRow } from "../components/ui.js";
import { workAttentionReason, workDisplayState, workHref } from "./work.js";

function currentWork(project) {
  const work = project?.work || {};
  return (work.live || []).find((item) => item.live)
    || (work.active || []).find((item) => item.status === "blocked")
    || (work.active || [])[0]
    || null;
}

function recentWork(project) {
  return (project?.work?.recent || []).slice(0, 5);
}

function mapFreshness(map) {
  if (map?.error) return "error";
  if (Number(map?.semantic_stale || 0) > 0 || Number(map?.semantic_missing || 0) > 0) return "stale";
  if (Number(map?.semantic_entries || 0) > 0 || Number(map?.semantic_current || 0) > 0) return "current";
  return "unknown";
}

function workMethod(work) {
  const runs = work?.runs || [];
  const run = runs.find((item) => item.role === "root" && !item.stale)
    || runs.find((item) => item.role === "root")
    || runs[0]
    || null;
  if (!run) return "host-native execution";
  return [run.host, run.client, run.assurance].filter(Boolean).join(" · ") || "host-native execution";
}

function changedLabel(work) {
  const delta = work?.repository_delta || {};
  const count = delta.changed_files ?? (work?.changed_paths || []).length;
  if (!count) return "без зафиксированных изменений";
  return `${count} ${count === 1 ? "файл" : "файлов"}`;
}

function checksLabel(work) {
  const checks = work?.checks || [];
  if (!checks.length) return "checks не зафиксированы";
  const passed = checks.filter((item) => item.status === "passed").length;
  const failed = checks.filter((item) => item.status === "failed").length;
  if (failed) return `${passed}/${checks.length} passed · ${failed} failed`;
  return `${passed}/${checks.length} passed`;
}

function lastAction(work) {
  const runs = work?.runs || [];
  const active = runs.find((item) => item.role === "root" && !item.stale) || runs[0];
  return active?.last_meaningful_action || work?.result_summary || "—";
}

function workOutcomeCard(projectKey, work, { compact = false } = {}) {
  const changed = (work?.changed_paths || []).slice(0, 3);
  const result = work?.result_summary || (work?.status === "completed" ? "Работа завершена" : lastAction(work));
  return `<a class="outcome-card ${compact ? "compact" : ""}" href="${workHref(projectKey, work.key)}">
    <div class="outcome-top">
      <span class="outcome-key">${escapeHtml(work.key || "Work")}</span>
      ${stateBadge(workDisplayState(work))}
    </div>
    <div class="outcome-title">${escapeHtml(work.goal || "—")}</div>
    <div class="outcome-result">${escapeHtml(result || "—")}</div>
    <div class="outcome-meta">
      <span>${escapeHtml(changedLabel(work))}</span>
      <span>${escapeHtml(checksLabel(work))}</span>
      <span>${escapeHtml(workMethod(work))}</span>
    </div>
    ${changed.length ? `<div class="outcome-paths">${changed.map((path) => `<code>${escapeHtml(path)}</code>`).join("")}${(work.changed_paths || []).length > changed.length ? `<span>+${escapeHtml((work.changed_paths || []).length - changed.length)}</span>` : ""}</div>` : ""}
    <div class="outcome-time">${escapeHtml(work.updated_at ? age(work.updated_at) : "")}</div>
  </a>`;
}

function taskCard(projectKey, task) {
  if (!task) return `<div class="empty">Managed Task ещё не использовался</div>`;
  const stage = task.active_stage;
  const open = task.finding_summary?.open ?? task.open_findings ?? 0;
  return `<a class="workspace-record" href="#/task/${encodeURIComponent(projectKey)}/${encodeURIComponent(task.key)}">
    <div class="workspace-record-main">
      <div class="record-kicker">${escapeHtml(task.key || "Task")} · ${escapeHtml(stage ? stageName(stage.kind) : "без активной стадии")}</div>
      <div class="record-title">${escapeHtml(task.goal || "—")}</div>
      <div class="record-meta">review ${escapeHtml(task.review_round ?? 0)} · fixes ${escapeHtml(task.fix_round ?? 0)} · ${escapeHtml(open)} findings</div>
    </div>
    ${stateBadge(task.status || "idle")}
  </a>`;
}

function epicCard(projectKey, epic) {
  const progress = epic.progress || {};
  return `<a class="workspace-record" href="#/epic/${encodeURIComponent(projectKey)}/${encodeURIComponent(epic.key)}">
    <div class="workspace-record-main">
      <div class="record-kicker">${escapeHtml(epic.key || "Epic")}</div>
      <div class="record-title">${escapeHtml(epic.title || "—")}</div>
      <div class="record-meta">${escapeHtml(progress.completed ?? 0)}/${escapeHtml(progress.total ?? 0)} plan items · ${escapeHtml(epic.updated_at ? age(epic.updated_at) : "")}</div>
    </div>
    ${stateBadge(epic.status || "idle")}
  </a>`;
}

function attentionItems(data) {
  const project = data.project || {};
  const task = project.task || {};
  const protocol = project.protocol_state || {};
  const freshness = mapFreshness(project.project_map || {});
  const items = [];
  for (const work of (project.work?.attention || []).slice(0, 4)) {
    items.push({
      title: `${work.key || "Work"} · ${work.goal || "Работа"}`,
      reason: workAttentionReason(work),
      href: workHref(project.key, work.key),
    });
  }
  if (task.human_attention_required) {
    items.push({ title: `${task.key || "Task"} требует решения`, reason: task.human_attention_reason || "human attention", href: `#/task/${encodeURIComponent(project.key)}/${encodeURIComponent(task.key)}` });
  }
  if (protocol.status === "warning") {
    items.push({ title: "Недавние protocol failures", reason: `${protocol.failures_5m || 0} за 5 минут`, href: hashUrl("monitoring", { project: project.key }) });
  }
  if (["stale", "error"].includes(freshness)) {
    items.push({ title: "Project Map требует обновления", reason: freshness, href: `#/project/${encodeURIComponent(project.key)}/knowledge` });
  }
  return items;
}

function attentionPanel(data) {
  const items = attentionItems(data);
  return `<section class="panel attention-panel ${items.length ? "has-attention" : ""}">
    <div class="panel-header"><div><div class="panel-title">Требует внимания</div><div class="panel-hint">Только то, что может остановить или исказить работу</div></div><span class="muted">${escapeHtml(items.length)}</span></div>
    ${items.length ? `<div class="attention-list">${items.map((item) => `<a class="attention-row" href="${item.href}"><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.reason || "проверить")}</span></div><span>→</span></a>`).join("")}</div>` : `<div class="calm-state"><strong>Ничего критичного</strong><span>Нет blocked/stale сигналов или решений пользователя.</span></div>`}
  </section>`;
}

function nowPanel(data) {
  const project = data.project || {};
  const work = currentWork(project);
  const task = ["active", "blocked"].includes(project.task?.status) ? project.task : null;
  if (!work && !task) {
    return `<section class="panel now-panel"><div class="panel-header"><div><div class="panel-title">Сейчас</div><div class="panel-hint">Текущий пользовательский фокус</div></div></div><div class="calm-state large"><strong>Проект в ожидании</strong><span>Активной работы нет. Последние результаты доступны ниже.</span></div></section>`;
  }
  return `<section class="panel now-panel">
    <div class="panel-header"><div><div class="panel-title">Сейчас</div><div class="panel-hint">Один текущий контекст вместо разрозненных экранов</div></div>${work ? stateBadge(workDisplayState(work)) : stateBadge(task?.status || "idle")}</div>
    ${work ? `<div class="now-focus">
      <div class="now-kicker">${escapeHtml(work.key || "Work")} · ${escapeHtml(work.kind || "work")}</div>
      <div class="now-title">${escapeHtml(work.goal || "—")}</div>
      <div class="now-action">${escapeHtml(lastAction(work))}</div>
      <div class="now-meta"><span>${escapeHtml(workMethod(work))}</span><span>${escapeHtml(changedLabel(work))}</span><span>${escapeHtml(checksLabel(work))}</span></div>
      <a class="panel-link" href="${workHref(project.key, work.key)}">Открыть ход работы →</a>
    </div>` : ""}
    ${task ? `<div class="managed-focus"><span class="managed-label">Managed workflow</span>${taskCard(project.key, task)}</div>` : ""}
  </section>`;
}

function recentResults(data) {
  const project = data.project || {};
  const items = recentWork(project);
  return `<section class="panel">
    <div class="panel-header"><div><div class="panel-title">Недавние результаты</div><div class="panel-hint">Что делали, что изменили, чем проверили и через какой host</div></div><a class="panel-header-link" href="#/project/${encodeURIComponent(project.key)}/work">Вся работа →</a></div>
    ${items.length ? `<div class="outcome-list">${items.map((work) => workOutcomeCard(project.key, work)).join("")}</div>` : `<div class="empty">Завершённой работы пока нет</div>`}
  </section>`;
}

function knowledgePulse(data) {
  const project = data.project || {};
  const map = project.project_map || {};
  const freshness = mapFreshness(map);
  const focusWork = currentWork(project);
  const focusTask = ["active", "blocked"].includes(project.task?.status) ? project.task : null;
  const focus = focusWork
    ? { kind: "Work", key: focusWork.key, title: focusWork.goal }
    : focusTask
      ? { kind: "Task", key: focusTask.key, title: focusTask.goal }
      : null;
  const catalogs = data.skill_state?.configured_catalog || {};
  const skillCount = Object.values(catalogs).reduce((sum, value) => sum + Number(value || 0), 0);
  return `<section class="panel">
    <div class="panel-header"><div><div class="panel-title">Контекст проекта</div><div class="panel-hint">То, что AI Layer уже знает и использует</div></div><a class="panel-header-link" href="#/project/${encodeURIComponent(project.key)}/knowledge">Знания →</a></div>
    <div class="info-list">
      ${infoRow("Current focus", focus ? `${focus.kind || "focus"} ${focus.key || ""}` : "новая работа", focus?.title || "")}
      ${infoRow("Project Map", `${map.semantic_current ?? 0} current · ${map.semantic_stale ?? 0} stale`, freshness)}
      ${infoRow("Memory refresh", project.memory_refresh?.status || "idle")}
      ${infoRow("Native skills", skillCount || "—", "user-level catalog")}
      ${infoRow("Privacy", project.mode || "standard")}
    </div>
  </section>`;
}

function projectHealth(data) {
  const project = data.project || {};
  const metrics = data.metrics || {};
  const agents = project.mcp_bridges || project.agents || [];
  return `<section class="panel">
    <div class="panel-header"><div><div class="panel-title">Система проекта</div><div class="panel-hint">Диагностика вторична по отношению к пользовательской работе</div></div><a class="panel-header-link" href="${hashUrl("monitoring", { project: project.key })}">Мониторинг →</a></div>
    <div class="info-list">
      ${infoRow("Protocol", project.protocol_state?.status || "healthy", project.protocol_state?.failures_5m ? `${project.protocol_state.failures_5m} failures / 5m` : "без recent failures")}
      ${infoRow("MCP p95", project.mcp_latency?.p95_ms != null ? `${project.mcp_latency.p95_ms} мс` : "—")}
      ${infoRow("Events / 24h", metrics.events_24h ?? 0)}
      ${infoRow("Failures / 24h", metrics.failures_24h ?? 0)}
    </div>
    <details class="technical-details"><summary><span>MCP bridges</span><span class="muted">${escapeHtml(agents.length)}</span></summary>${agentsList(agents)}</details>
  </section>`;
}

function projectHeader(project) {
  return `<div class="project-head workspace-project-head">
    <div><div class="section-eyebrow">PROJECT WORKSPACE</div><h2>${escapeHtml(project.name || "Проект")}</h2><div class="path">${escapeHtml(project.root || "")}</div></div>
    ${stateBadge(project.project_state || "healthy")}
  </div>`;
}

export function renderProject(data) {
  const project = data.project || {};
  const work = project.work || {};
  const recent = recentWork(project);
  const active = currentWork(project);
  const attention = attentionItems(data);
  return `
    ${projectHeader(project)}
    <div class="workspace-summary-grid">
      ${metric("Сейчас", active ? active.key : "пауза", active?.goal || "активной работы нет")}
      ${metric("Нужно внимания", attention.length, attention.length ? "есть actionable сигналы" : "всё спокойно")}
      ${metric("Недавние результаты", recent.length, recent[0]?.updated_at ? `последний ${age(recent[0].updated_at)}` : "истории пока нет")}
      ${metric("Project Map", project.project_map?.semantic_current_coverage != null ? `${Math.round(Number(project.project_map.semantic_current_coverage || 0) * 100)}%` : "—", `${escapeHtml(project.project_map?.semantic_current ?? 0)} current`)}
    </div>
    <div class="dashboard-grid project-workspace-layout">
      <div class="dashboard-main">
        ${nowPanel(data)}
        ${recentResults(data)}
      </div>
      <div class="dashboard-side">
        ${attentionPanel(data)}
        ${knowledgePulse(data)}
        ${projectHealth(data)}
      </div>
    </div>`;
}

function groupedWork(projectKey, items) {
  if (!items.length) return `<div class="empty">WorkItems ещё не создавались</div>`;
  return `<div class="outcome-list">${items.map((work) => workOutcomeCard(projectKey, work, { compact: true })).join("")}</div>`;
}

function taskList(projectKey, items) {
  if (!items.length) return `<div class="empty">Managed Tasks ещё не создавались</div>`;
  return `<div class="workspace-record-list">${items.map((task) => taskCard(projectKey, task)).join("")}</div>`;
}

function epicList(projectKey, items) {
  if (!items.length) return `<div class="empty">Эпиков ещё не было</div>`;
  return `<div class="workspace-record-list">${items.map((epic) => epicCard(projectKey, epic)).join("")}</div>`;
}

export function renderProjectWorkHub(data) {
  const project = data.projectData?.project || {};
  const works = data.work?.items || [];
  const tasks = data.tasks?.items || [];
  const epics = data.epics?.items || [];
  const current = works.filter((item) => ["active", "blocked"].includes(item.status)).slice(0, 4);
  const recent = works.filter((item) => !["active", "blocked"].includes(item.status)).slice(0, 6);
  return `
    ${projectHeader(project)}
    <div class="page-intro"><div><div class="section-eyebrow">WORK</div><div class="section-heading">Вся работа проекта в одном месте</div><p>Ordinary Work показывает реальное выполнение. Managed Task и Epic добавляют assurance и структуру, не подменяя саму работу.</p></div></div>
    <div class="dashboard-grid project-workspace-layout">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Текущая работа</div><div class="panel-hint">Active и blocked WorkItems</div></div><a class="panel-header-link" href="${hashUrl("work", { project: project.key })}">Все Work →</a></div>
          ${groupedWork(project.key, current)}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Последние результаты</div><div class="panel-hint">Terminal WorkItems с изменениями, checks и execution evidence</div></div><a class="panel-header-link" href="${hashUrl("work", { project: project.key, status: "completed" })}">История Work →</a></div>
          ${groupedWork(project.key, recent)}
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Managed Tasks</div><div class="panel-hint">Строгий workflow только там, где он нужен</div></div><a class="panel-header-link" href="${hashUrl("tasks", { project: project.key })}">Все →</a></div>
          ${taskList(project.key, tasks.slice(0, 5))}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Эпики</div><div class="panel-hint">Длинные инициативы и их прогресс</div></div><a class="panel-header-link" href="${hashUrl("epics", { project: project.key })}">Все →</a></div>
          ${epicList(project.key, epics.slice(0, 5))}
        </section>
      </div>
    </div>`;
}

function knowledgeCard(projectKey, item) {
  return `<a class="knowledge-summary-card" href="#/knowledge-card/${encodeURIComponent(projectKey)}/${encodeURIComponent(item.id)}">
    <div class="knowledge-summary-top"><span>${escapeHtml(item.category || "knowledge")}</span>${stateBadge(String(item.status || "verified").toLowerCase())}</div>
    <strong>${escapeHtml(item.title || item.key || "Knowledge")}</strong>
    <p>${escapeHtml(item.summary || "")}</p>
    <span class="record-time">${escapeHtml(item.updated_at ? age(item.updated_at) : "")}</span>
  </a>`;
}

function skillCard(item, projectKey) {
  return `<a class="workspace-record" href="${hashUrl(`skill/${encodeURIComponent(item.slug)}`, { project: projectKey })}">
    <div class="workspace-record-main"><div class="record-kicker">${escapeHtml(item.scope || "global")}</div><div class="record-title">${escapeHtml(item.slug || "skill")}</div><div class="record-meta">${escapeHtml(item.description || "")}</div></div><span>→</span>
  </a>`;
}

export function renderProjectKnowledgeHub(data) {
  const project = data.projectData?.project || {};
  const map = project.project_map || {};
  const freshness = mapFreshness(map);
  const summary = data.knowledge?.summary || {};
  const knowledge = data.knowledge?.items || [];
  const skills = data.skills?.items || [];
  const rules = data.rules?.project || {};
  return `
    ${projectHeader(project)}
    <div class="workspace-summary-grid">
      ${metric("Verified knowledge", summary.verified ?? 0, `${summary.stale ?? 0} stale · ${summary.draft ?? 0} draft`)}
      ${metric("Project Map", `${escapeHtml(map.semantic_current ?? 0)} current`, `${escapeHtml(map.semantic_stale ?? 0)} stale · ${escapeHtml(map.semantic_missing ?? 0)} missing`)}
      ${metric("Project rules", rules.rule_count ?? 0, rules.has_custom_rules ? "custom" : "только global policy")}
      ${metric("Skills", data.skills?.pagination?.total ?? skills.length, "доступно в контексте проекта")}
    </div>
    <div class="dashboard-grid project-workspace-layout">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Project Knowledge</div><div class="panel-hint">Проверенные знания, ограничения и evidence</div></div><a class="panel-header-link" href="${hashUrl("knowledge", { project: project.key, status: "ALL" })}">Вся база →</a></div>
          ${knowledge.length ? `<div class="knowledge-summary-list">${knowledge.map((item) => knowledgeCard(project.key, item)).join("")}</div>` : `<div class="empty">Knowledge cards пока нет</div>`}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Project Map</div><div class="panel-hint">Где находится код и насколько карта свежая</div></div>${stateBadge(freshness)}</div>
          <div class="info-list">
            ${infoRow("Semantic entries", map.semantic_entries ?? "—")}
            ${infoRow("Current", map.semantic_current ?? "—")}
            ${infoRow("Stale / missing", `${map.semantic_stale ?? 0} / ${map.semantic_missing ?? 0}`)}
            ${infoRow("Freshness", freshness)}
            ${infoRow("Execution owner", "host-native")}
          </div>
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Правила проекта</div><div class="panel-hint">Только project-specific правила поверх global policy</div></div><a class="panel-header-link" href="${hashUrl("rules", { project: project.key })}">Открыть →</a></div>
          ${rules.has_custom_rules ? `<div class="rule-preview">${escapeHtml(String(rules.content || "").slice(0, 900))}</div>` : `<div class="calm-state"><strong>Нет локальных правил</strong><span>Используется глобальная policy AI Layer.</span></div>`}
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Skills</div><div class="panel-hint">Что доступно host-у в контексте этого проекта</div></div><a class="panel-header-link" href="${hashUrl("skills", { project: project.key })}">Каталог →</a></div>
          ${skills.length ? `<div class="workspace-record-list">${skills.map((item) => skillCard(item, project.key)).join("")}</div>` : `<div class="empty">Skills не найдены</div>`}
        </section>
      </div>
    </div>`;
}
