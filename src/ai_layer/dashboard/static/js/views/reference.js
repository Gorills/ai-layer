import { age, escapeHtml } from "../format.js";
import { metric, stateBadge } from "../components/common.js";
import { compactList, filterTabs, hashUrl, markdown, pagination, projectPicker } from "../components/ui.js";

export function renderSkills(payload, route) {
  const project = payload.project_key || route.project || null;
  return `
    <div class="page-toolbar">
      <div><div class="section-eyebrow">EXPERTISE</div><div class="section-heading">Скиллы</div></div>
      <div class="toolbar-controls">${projectPicker(payload.projects || [], project, "skills")}</div>
    </div>
    <section class="panel">
      <div class="panel-header"><div><div class="panel-title">Каталог</div><div class="panel-hint">Краткое представление; полный контент открывается отдельно и не грузится в список.</div></div><span class="muted">${escapeHtml(payload.pagination?.total || 0)} skills</span></div>
      <div class="skill-browser">${(payload.items || []).map((skill) => `<a class="skill-browser-row" href="${hashUrl(`skill/${encodeURIComponent(skill.slug)}`, { project })}">
        <div class="skill-browser-main">
          <div class="record-kicker">${escapeHtml(skill.scope || "global")} · ${escapeHtml(skill.section_count || 0)} разделов${skill.risk ? ` · ${escapeHtml(skill.risk)}` : ""}</div>
          <div class="record-title">${escapeHtml(skill.slug)}</div>
          <div class="record-description">${escapeHtml(skill.description || skill.core_preview || "Описание не задано")}</div>
        </div>
        <span class="soft-arrow">→</span>
      </a>`).join("") || `<div class="empty">Скиллы не найдены</div>`}</div>
      <div class="panel-footer"><span class="muted">Показывается по 10 записей</span>${pagination(payload.pagination, "skills", { project })}</div>
    </section>`;
}

export function renderSkillDetail(payload, route) {
  const mode = route.mode === "full" ? "full" : "short";
  const project = route.project || null;
  const content = mode === "full" ? payload.content : payload.core;
  return `
    <div class="detail-hero compact-hero">
      <div>
        <a class="back-link" href="${hashUrl("skills", { project })}">← Каталог скиллов</a>
        <div class="detail-kicker">${escapeHtml(payload.scope || "global")} skill</div>
        <h2>${escapeHtml(payload.slug || "Skill")}</h2>
        <div class="detail-subtitle">${escapeHtml(payload.description || "")}</div>
      </div>
      ${payload.risk ? stateBadge(payload.risk === "high" ? "warning" : "healthy") : ""}
    </div>
    <section class="panel">
      <div class="panel-header panel-header-wrap">
        <div><div class="panel-title">Содержимое</div><div class="panel-hint">Краткий режим показывает core; полный — исходный skill целиком.</div></div>
        ${filterTabs([{ label: "Краткий", value: "short" }, { label: "Полный", value: "full" }], mode, `skill/${encodeURIComponent(payload.slug)}`, { project }, "mode")}
      </div>
      <article class="document-view">${markdown(content || "")}</article>
    </section>`;
}

export function renderRules(payload, route) {
  const project = route.project || payload.project?.key || null;
  return `
    <div class="page-toolbar">
      <div><div class="section-eyebrow">POLICY</div><div class="section-heading">Правила</div></div>
      <div class="toolbar-controls">${projectPicker(payload.projects || [], project, "rules")}</div>
    </div>
    <div class="summary-grid">
      ${metric("Глобальные правила", payload.global?.rule_count ?? 0, payload.global?.customized ? "локально изменены" : "bundled policy")}
      ${metric("Правила проекта", payload.project?.rule_count ?? 0, payload.project ? payload.project.name : "проект не выбран")}
      ${metric("Strict private", payload.project?.strict_private ? "Включён" : "Нет", payload.project?.privacy || "—")}
      ${metric("Источник", "Локальный", "без аккаунтов и профилей")}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Global policy</div><div class="panel-hint">Базовые обязательные правила AI Layer</div></div></div>
          <article class="document-view">${markdown(payload.global?.content || "")}</article>
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Project rules</div><div class="panel-hint">Только правила выбранного репозитория</div></div></div>
          ${payload.project ? (payload.project.content ? `<article class="document-view compact-document">${markdown(payload.project.content)}</article>` : `<div class="empty">У проекта нет дополнительных правил</div>`) : `<div class="empty">Выберите проект</div>`}
        </section>
        ${payload.project?.strict_private ? `<div class="notice warning"><strong>Strict private.</strong> AI Layer artifacts и AI-development provenance не должны попадать в репозиторий.</div>` : ""}
      </div>
    </div>`;
}

function knowledgeCard(card, projectKey) {
  return `<a class="knowledge-row" href="${hashUrl(`knowledge-card/${projectKey}/${card.id}`)}">
    <div class="knowledge-icon">${escapeHtml((card.category || "K").slice(0, 1).toUpperCase())}</div>
    <div class="knowledge-main">
      <div class="record-kicker">${escapeHtml(card.category || "other")} · ${escapeHtml(card.status || "DRAFT")}</div>
      <div class="record-title">${escapeHtml(card.title || card.key || "Knowledge")}</div>
      <div class="record-description">${escapeHtml(card.summary || "—")}</div>
      <div class="record-meta">${escapeHtml((card.source_pointers || []).slice(0, 3).join(" · "))}</div>
    </div>
    <div class="record-side"><span class="record-time">${escapeHtml(card.updated_at ? age(card.updated_at) : "")}</span><span class="soft-arrow">→</span></div>
  </a>`;
}

export function renderKnowledge(payload, route) {
  const project = payload.project?.key || route.project;
  const status = payload.status || route.status || "VERIFIED";
  const summary = payload.summary || {};
  return `
    <div class="page-toolbar">
      <div><div class="section-eyebrow">PROJECT MEMORY</div><div class="section-heading">База знаний</div></div>
      <div class="toolbar-controls">${projectPicker(payload.projects || [], project, "knowledge", { status }, { allowAll: false })}</div>
    </div>
    <div class="summary-grid">
      ${metric("Verified", summary.verified ?? 0, "review-gated")}
      ${metric("Draft", summary.draft ?? 0, "ожидают независимого review")}
      ${metric("Stale", summary.stale ?? 0, "evidence изменился")}
      ${metric("Subsystems", summary.verified_subsystems ?? 0, summary.baseline_ready ? "baseline готов" : "onboarding recommended")}
    </div>
    <section class="panel">
      <div class="panel-header panel-header-wrap">
        <div><div class="panel-title">Knowledge cards</div><div class="panel-hint">Семантические знания проекта с evidence pointers; source code остаётся авторитетом.</div></div>
        ${filterTabs([
          { label: "Verified", value: "VERIFIED" },
          { label: "Draft", value: "DRAFT" },
          { label: "Stale", value: "STALE" },
          { label: "Все", value: "ALL" },
        ], status, "knowledge", { project }, "status")}
      </div>
      <div class="knowledge-list">${(payload.items || []).map((card) => knowledgeCard(card, project)).join("") || `<div class="empty">Карточек в этом состоянии нет</div>`}</div>
      <div class="panel-footer"><span class="muted">${escapeHtml(payload.pagination?.total || 0)} записей</span>${pagination(payload.pagination, "knowledge", { project, status })}</div>
    </section>`;
}

export function renderKnowledgeDetail(payload) {
  const card = payload.card || {};
  const project = payload.project || {};
  return `
    <div class="detail-hero compact-hero">
      <div>
        <a class="back-link" href="${hashUrl("knowledge", { project: project.key })}">← База знаний</a>
        <div class="detail-kicker">${escapeHtml(project.name || "Проект")} · ${escapeHtml(card.category || "knowledge")}</div>
        <h2>${escapeHtml(card.title || card.key || "Knowledge")}</h2>
        <div class="detail-subtitle">${escapeHtml(card.summary || "")}</div>
      </div>
      ${stateBadge(String(card.status || "draft").toLowerCase() === "verified" ? "completed" : String(card.status || "draft").toLowerCase() === "stale" ? "warning" : "idle")}
    </div>
    <div class="dashboard-grid">
      <div class="dashboard-main">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Знание</div><div class="panel-hint">Полный сохранённый текст карточки</div></div></div>
          <article class="document-view">${markdown(card.content || "")}</article>
        </section>
      </div>
      <div class="dashboard-side">
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Claims</div><div class="panel-hint">Проверенные утверждения</div></div></div>
          <div class="content-block">${compactList(card.claims, "Нет claims")}</div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Constraints</div><div class="panel-hint">Инварианты и ограничения</div></div></div>
          <div class="content-block">${compactList(card.constraints, "Нет constraints")}</div>
        </section>
        <section class="panel">
          <div class="panel-header"><div><div class="panel-title">Evidence</div><div class="panel-hint">Файлы, на которых основана карточка</div></div></div>
          <div class="content-block">${compactList(card.source_pointers, "Нет evidence")}</div>
        </section>
      </div>
    </div>`;
}
