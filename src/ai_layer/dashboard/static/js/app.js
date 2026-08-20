import { api } from "./api.js";
import { hashUrl } from "./components/ui.js";
import { time, escapeHtml } from "./format.js";
import { renderEpicDetail, renderEpics } from "./views/epic.js";
import { renderOverview } from "./views/overview.js";
import { renderProject, renderProjectKnowledgeHub, renderProjectWorkHub } from "./views/project.js";
import { renderActivity, renderMonitoring, renderTaskDetail, renderTasks } from "./views/operations.js";
import { renderKnowledge, renderKnowledgeDetail, renderRules, renderSkillDetail, renderSkills } from "./views/reference.js";
import { renderWorkDetail, renderWorkList } from "./views/work.js";

const app = document.querySelector("#app");
const projectScope = document.querySelector("#project-scope");
const projectHomeNav = document.querySelector("#project-home-nav");
const pageTitle = document.querySelector("#page-title");
const pageSubtitle = document.querySelector("#page-subtitle");
const updatedAt = document.querySelector("#updated-at");
const dot = document.querySelector("#connection-dot");
const connectionLabel = document.querySelector("#connection-label");
const sidebarVersion = document.querySelector("#sidebar-version");
const refreshButton = document.querySelector("#refresh-button");

const ACTIVE_POLL_MS = 3000;
const IDLE_POLL_MS = 12000;
const VOLATILE_RENDER_FIELDS = new Set(["generated_at", "uptime_seconds", "idle_seconds"]);
const FILTERABLE_ROOTS = new Set(["work", "tasks", "epics", "skills", "rules", "knowledge", "monitoring", "activity"]);

let overviewCache = null;
let overviewCachedAt = 0;
let timer = null;
let loadPromise = null;
let reloadRequested = false;
let nextPollMs = IDLE_POLL_MS;
let lastRenderFingerprint = null;
let lastScopeFingerprint = null;

const PROJECT_COCKPIT_CACHE_MS = IDLE_POLL_MS;
const projectCockpitCache = new Map();

async function projectCockpitData(projectKey) {
  const cached = projectCockpitCache.get(projectKey);
  if (cached && Date.now() - cached.cachedAt < PROJECT_COCKPIT_CACHE_MS) return cached.data;
  const [tasks, epics] = await Promise.all([
    api.tasks({ project_key: projectKey, page: 1, page_size: 6 }),
    api.epics({ project_key: projectKey, page: 1, page_size: 6 }),
  ]);
  const data = { tasks, epics };
  projectCockpitCache.set(projectKey, { cachedAt: Date.now(), data });
  return data;
}

function intParam(params, name, fallback = 1) {
  const value = Number(params.get(name) || fallback);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

function route() {
  const raw = location.hash.replace(/^#\/?/, "") || "overview";
  const [pathValue, queryValue = ""] = raw.split("?", 2);
  const parts = pathValue.split("/").filter(Boolean);
  const params = new URLSearchParams(queryValue);
  const common = {
    project: params.get("project") || null,
    status: params.get("status") || null,
    mode: params.get("mode") || null,
    page: intParam(params, "page", 1),
    cursor: params.get("cursor") || null,
    occurredAfter: params.get("occurred_after") || null,
    occurredBefore: params.get("occurred_before") || null,
    workId: params.get("work_id") || null,
    taskId: params.get("task_id") || null,
    epicId: params.get("epic_id") || null,
    actorId: params.get("actor_id") || null,
    eventType: params.get("event_type") || null,
    importance: params.get("importance") || null,
    assurance: params.get("assurance") || null,
  };
  if (parts[0] === "project" && parts[1]) {
    const key = decodeURIComponent(parts[1]);
    if (parts[2] === "work") return { kind: "project-work", key, ...common };
    if (parts[2] === "knowledge") return { kind: "project-knowledge", key, ...common };
    return { kind: "project", key, ...common };
  }
  if (parts[0] === "epic" && parts[1] && parts[2]) return { kind: "epic", projectKey: decodeURIComponent(parts[1]), epicKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "task" && parts[1] && parts[2]) return { kind: "task", projectKey: decodeURIComponent(parts[1]), taskKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "work" && parts[1] && parts[2]) return { kind: "work-item", projectKey: decodeURIComponent(parts[1]), workKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "skill" && parts[1]) return { kind: "skill", slug: decodeURIComponent(parts[1]), ...common };
  if (parts[0] === "knowledge-card" && parts[1] && parts[2]) return { kind: "knowledge-card", projectKey: decodeURIComponent(parts[1]), knowledgeId: decodeURIComponent(parts[2]), ...common };
  if (["work", "tasks", "epics", "skills", "rules", "knowledge", "monitoring", "activity"].includes(parts[0])) return { kind: parts[0], ...common };
  return { kind: "overview", ...common };
}

function routeKey(current) { return JSON.stringify(current); }

function semanticFingerprint(current, payload) {
  return JSON.stringify([routeKey(current), payload], (key, value) => VOLATILE_RENDER_FIELDS.has(key) ? undefined : value);
}

function setConnection(ok, label) {
  dot.classList.toggle("online", ok);
  dot.classList.toggle("offline", !ok);
  connectionLabel.textContent = label;
}

function routeIsCurrent(current) {
  return routeKey(current) === routeKey(route());
}

function overviewCacheExpired() {
  return !overviewCache || Date.now() - overviewCachedAt >= IDLE_POLL_MS;
}

function setNavigationBusy(busy) {
  document.body.dataset.navigationLoading = busy ? "true" : "false";
  app.setAttribute("aria-busy", busy ? "true" : "false");
  refreshButton.disabled = busy;
  if (busy) updatedAt.textContent = "обновляю…";
}

function showRefreshWarning(error) {
  let warning = app.querySelector("[data-refresh-warning]");
  if (!warning) {
    app.insertAdjacentHTML(
      "afterbegin",
      '<div class="alert dashboard-refresh-warning" data-refresh-warning="true"></div>',
    );
    warning = app.querySelector("[data-refresh-warning]");
  }
  if (warning) warning.textContent = `Не удалось обновить данные: ${error?.message || "ошибка сети"}`;
}

function clearRefreshWarning() {
  app.querySelector("[data-refresh-warning]")?.remove();
}

function keepCurrentRoute(current) {
  if (routeIsCurrent(current)) return true;
  reloadRequested = true;
  return false;
}

function rootRoute(kind) {
  if (["work-item", "work", "project-work"].includes(kind)) return "work";
  if (["task", "tasks"].includes(kind)) return "tasks";
  if (["epic", "epics"].includes(kind)) return "epics";
  if (["skill", "skills"].includes(kind)) return "skills";
  if (["knowledge", "knowledge-card", "project-knowledge"].includes(kind)) return "knowledge";
  if (kind === "project") return "project";
  return kind;
}

function projectForRoute(current) {
  if (["project", "project-work", "project-knowledge"].includes(current.kind)) return current.key;
  if (["epic", "task", "knowledge-card", "work-item"].includes(current.kind)) return current.projectKey;
  return current.project || null;
}

function projectSection(current) {
  if (["project-work", "work", "work-item", "tasks", "task", "epics", "epic"].includes(current.kind)) return "work";
  if (["project-knowledge", "knowledge", "knowledge-card", "skills", "skill", "rules"].includes(current.kind)) return "knowledge";
  if (current.kind === "activity") return "activity";
  if (current.kind === "monitoring") return "monitoring";
  return "summary";
}

function scopedHref(root, projectKey) {
  if (root === "overview") return "#/overview";
  if (root === "project") return projectKey ? `#/project/${encodeURIComponent(projectKey)}` : "#/overview";
  if (projectKey && root === "work") return `#/project/${encodeURIComponent(projectKey)}/work`;
  if (projectKey && root === "knowledge") return `#/project/${encodeURIComponent(projectKey)}/knowledge`;
  if (FILTERABLE_ROOTS.has(root)) return hashUrl(root, { project: projectKey || null });
  return `#/${root}`;
}

function renderNav(data) {
  const projects = data.projects || [];
  const fingerprint = JSON.stringify(projects.map((project) => [project.key, project.name]));
  if (fingerprint !== lastScopeFingerprint) {
    projectScope.innerHTML = `<option value="">Все проекты</option>${projects.map((project) => `<option value="${escapeHtml(project.key)}">${escapeHtml(project.name)}</option>`).join("")}`;
    lastScopeFingerprint = fingerprint;
  }
  const current = route();
  const selectedProject = projectForRoute(current);
  const knownProject = projects.some((project) => project.key === selectedProject) ? selectedProject : null;
  projectScope.value = knownProject || "";

  if (projectHomeNav) {
    projectHomeNav.href = scopedHref("project", knownProject);
    projectHomeNav.classList.toggle("unavailable", !knownProject);
    projectHomeNav.setAttribute("aria-disabled", knownProject ? "false" : "true");
  }

  document.querySelectorAll(".nav-item[data-route]").forEach((element) => {
    const target = element.dataset.route;
    element.classList.remove("active");
    element.href = scopedHref(target, knownProject);
  });
  document.querySelector(`[data-route="${CSS.escape(rootRoute(current.kind))}"]`)?.classList.add("active");
  document.body.dataset.route = rootRoute(current.kind);
  document.body.dataset.projectContext = knownProject ? "selected" : "portfolio";
}

function projectContextBar(current, data) {
  const key = projectForRoute(current);
  if (!key) return "";
  const project = (data.projects || []).find((item) => item.key === key);
  if (!project) return "";
  const section = projectSection(current);
  const links = [
    ["summary", "Сводка", `#/project/${encodeURIComponent(key)}`],
    ["work", "Работа", `#/project/${encodeURIComponent(key)}/work`],
    ["knowledge", "Знания", `#/project/${encodeURIComponent(key)}/knowledge`],
    ["activity", "История", hashUrl("activity", { project: key })],
    ["monitoring", "Система", hashUrl("monitoring", { project: key })],
  ];
  return `<div class="project-context-bar">
    <a class="project-context-identity" href="#/project/${encodeURIComponent(key)}">
      <span class="project-context-label">Проект</span>
      <strong>${escapeHtml(project.name || key)}</strong>
    </a>
    <nav class="project-context-tabs" aria-label="Разделы проекта">
      ${links.map(([value, label, href]) => `<a class="project-context-tab ${section === value ? "active" : ""}" href="${href}">${label}</a>`).join("")}
    </nav>
  </div>`;
}

function navigateScope(projectKey) {
  const current = route();
  if (["project", "project-work", "project-knowledge"].includes(current.kind)) {
    const suffix = current.kind === "project-work" ? "/work" : current.kind === "project-knowledge" ? "/knowledge" : "";
    location.hash = projectKey ? `#/project/${encodeURIComponent(projectKey)}${suffix}` : "#/overview";
    return;
  }
  const root = rootRoute(current.kind);
  if (current.kind === "overview") {
    location.hash = projectKey ? `#/project/${encodeURIComponent(projectKey)}` : "#/overview";
    return;
  }
  if (FILTERABLE_ROOTS.has(root)) {
    location.hash = hashUrl(root, {
      project: projectKey || null,
      status: current.status || null,
      mode: current.mode || null,
    });
    return;
  }
  location.hash = projectKey ? `#/project/${encodeURIComponent(projectKey)}` : "#/overview";
}

function bindDynamicControls() {
  document.querySelectorAll("[data-project-key]").forEach((row) => row.addEventListener("click", () => { location.hash = `#/project/${encodeURIComponent(row.dataset.projectKey)}`; }));
  document.querySelectorAll("[data-history-back]").forEach((button) => button.addEventListener("click", () => history.back()));
  document.querySelectorAll("form[data-hash-form]").forEach((form) => form.addEventListener("submit", (event) => {
    event.preventDefault();
    location.hash = hashUrl(form.dataset.hashPath, Object.fromEntries(new FormData(form).entries()));
  }));
  document.querySelectorAll("select[data-hash-select]").forEach((select) => select.addEventListener("change", () => {
    if (select.value) location.hash = select.value.startsWith("#") ? select.value.slice(1) : select.value;
  }));
  document.querySelectorAll('form[data-work-complete="true"]').forEach((form) => form.addEventListener("submit", () => {
    const button = form.querySelector('[data-work-complete-button="true"]');
    if (!button) return;
    button.disabled = true;
    button.textContent = "Завершаю…";
  }));
}

function overviewIsLive(data) {
  const summary = data?.summary || {};
  return Number(summary.active_work || 0) > 0 || Number(summary.active_tasks || 0) > 0 || Number(summary.active_agents || 0) > 0;
}

function projectIsLive(data) {
  const project = data?.project || {};
  const task = data?.task_state?.current || {};
  return project.runtime_state === "active" || project.project_state === "working" || task.status === "active" || (project.active_operations || []).length > 0;
}

function epicIsLive(data) { return ["phase0", "planning", "running", "final_review"].includes(data?.epic?.status || ""); }
function epicsAreLive(data) { return (data?.items || []).some((item) => ["phase0", "planning", "running", "final_review"].includes(item.status || "")); }

function renderChanged(current, payload, render) {
  if (!keepCurrentRoute(current)) return false;
  const fingerprint = semanticFingerprint(current, payload);
  if (fingerprint === lastRenderFingerprint) return false;
  lastRenderFingerprint = fingerprint;
  render();
  const context = projectContextBar(current, overviewCache || {});
  if (context) app.insertAdjacentHTML("afterbegin", context);
  bindDynamicControls();
  return true;
}

function setPage(title, subtitle) {
  pageTitle.textContent = title;
  pageSubtitle.textContent = subtitle;
}

function projectRequired(title) {
  const projects = overviewCache?.projects || [];
  return `<div class="project-required">
    <div class="section-eyebrow">${escapeHtml(title)}</div>
    <h2>Сначала выберите проект</h2>
    <p>Этот раздел имеет смысл только внутри конкретного проекта. Выбор сохранится при дальнейшей навигации.</p>
    <div class="project-choice-grid">${projects.map((project) => `<a class="project-choice" href="#/project/${encodeURIComponent(project.key)}/knowledge"><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.root || "")}</span></a>`).join("") || `<div class="empty">Зарегистрированных проектов нет</div>`}</div>
  </div>`;
}

async function loadCycle() {
  const current = route();
  try {
    if (overviewCacheExpired() || current.kind === "overview" || current.kind === "monitoring") {
      overviewCache = await api.overview();
      overviewCachedAt = Date.now();
    }
    renderNav(overviewCache);

    let generatedAt = overviewCache.generated_at;
    if (current.kind === "work") {
      const data = await api.work({ project_key: current.project, status: current.status, page: current.page, page_size: 10 });
      renderChanged(current, data, () => {
        setPage("Работа", current.project ? "Work выбранного проекта" : "WorkItems по всем проектам");
        app.innerHTML = renderWorkList(data, current);
      });
      generatedAt = data.generated_at || overviewCache.generated_at;
      nextPollMs = (data.items || []).some((item) => item.live) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "work-item") {
      const data = await api.workDetail(current.projectKey, current.workKey);
      renderChanged(current, data, () => {
        setPage(`${data.work?.key || "Work"} · ${data.work?.goal || ""}`, "Результат, изменения, проверки и ход выполнения");
        app.innerHTML = renderWorkDetail(data);
      });
      generatedAt = data.work?.updated_at;
      nextPollMs = data.work?.live ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "project") {
      const [projectData, cockpit] = await Promise.all([
        api.project(current.key),
        projectCockpitData(current.key),
      ]);
      const data = { ...projectData, tasks: cockpit.tasks, epics: cockpit.epics };
      renderChanged(current, data, () => {
        setPage(data.project?.name || "Проект", "Cockpit: текущая работа, решения, Tasks, Epics и последние результаты");
        app.innerHTML = renderProject(data);
      });
      generatedAt = projectData.generated_at;
      nextPollMs = projectIsLive(projectData) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "project-work") {
      const [projectData, work, tasks, epics] = await Promise.all([
        api.project(current.key),
        api.work({ project_key: current.key, page: 1, page_size: 8 }),
        api.tasks({ project_key: current.key, page: 1, page_size: 6 }),
        api.epics({ project_key: current.key, page: 1, page_size: 6 }),
      ]);
      const data = { projectData, work, tasks, epics };
      renderChanged(current, data, () => {
        setPage(projectData.project?.name || "Проект", "Work, Managed Tasks и Epics в одном рабочем контексте");
        app.innerHTML = renderProjectWorkHub(data);
      });
      generatedAt = projectData.generated_at || work.generated_at;
      nextPollMs = projectIsLive(projectData) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "project-knowledge") {
      const [projectData, knowledge, skills, rules] = await Promise.all([
        api.project(current.key),
        api.knowledge(current.key, { status: "ALL", page: 1, page_size: 6 }),
        api.skills({ project_key: current.key, page: 1, page_size: 6 }),
        api.rules(current.key),
      ]);
      const data = { projectData, knowledge, skills, rules };
      renderChanged(current, data, () => {
        setPage(projectData.project?.name || "Проект", "Project Knowledge, правила, карта и доступные skills");
        app.innerHTML = renderProjectKnowledgeHub(data);
      });
      generatedAt = projectData.generated_at;
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "epics") {
      const data = await api.epics({ project_key: current.project, status: current.status, page: current.page, page_size: 10 });
      renderChanged(current, data, () => {
        setPage("Эпики", current.project ? "Крупные инициативы выбранного проекта" : "Крупные инициативы по всем проектам");
        app.innerHTML = renderEpics(data, current);
      });
      generatedAt = data.generated_at || overviewCache.generated_at;
      nextPollMs = epicsAreLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "epic") {
      const data = await api.epic(current.projectKey, current.epicKey);
      renderChanged(current, data, () => {
        setPage(`${data.epic?.key || "Epic"} · ${data.epic?.title || ""}`, "Specification, Tasks, audits и final review");
        app.innerHTML = renderEpicDetail(data, current);
      });
      generatedAt = data.epic?.updated_at;
      nextPollMs = epicIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "tasks") {
      const data = await api.tasks({ project_key: current.project, status: current.status, page: current.page, page_size: 10 });
      renderChanged(current, data, () => { setPage("Managed Tasks", current.project ? "Managed workflow выбранного проекта" : "Managed workflow по всем проектам"); app.innerHTML = renderTasks(data, current); });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "task") {
      const data = await api.task(current.projectKey, current.taskKey);
      renderChanged(current, data, () => { setPage(`${data.task?.key || "Task"}`, "Стадии, review findings, verification и model assurance"); app.innerHTML = renderTaskDetail(data); });
      nextPollMs = data.task?.status === "active" ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "skills") {
      const data = await api.skills({ project_key: current.project, page: current.page, page_size: 10 });
      renderChanged(current, data, () => { setPage("Скиллы", current.project ? "Skills, доступные в контексте проекта" : "Глобальный каталог skills"); app.innerHTML = renderSkills(data, current); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "skill") {
      const data = await api.skill(current.slug, current.project);
      renderChanged(current, data, () => { setPage(data.slug || "Skill", "Краткий core или полный skill"); app.innerHTML = renderSkillDetail(data, current); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "rules") {
      const data = await api.rules(current.project);
      renderChanged(current, data, () => { setPage("Правила", current.project ? "Глобальная policy и правила выбранного проекта" : "Глобальная policy"); app.innerHTML = renderRules(data, current); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "knowledge") {
      if (!current.project) {
        renderChanged(current, overviewCache, () => { setPage("База знаний", "Project Knowledge всегда принадлежит конкретному проекту"); app.innerHTML = projectRequired("База знаний"); });
        nextPollMs = IDLE_POLL_MS;
      } else {
        const data = await api.knowledge(current.project, { status: current.status || "VERIFIED", page: current.page, page_size: 10 });
        renderChanged(current, data, () => { setPage("База знаний", "Проверенные знания и review-gated drafts выбранного проекта"); app.innerHTML = renderKnowledge(data, current); });
        nextPollMs = IDLE_POLL_MS;
      }
    } else if (current.kind === "knowledge-card") {
      const data = await api.knowledgeDetail(current.projectKey, current.knowledgeId);
      renderChanged(current, data, () => { setPage(data.card?.title || "Knowledge", "Claims, constraints, unknowns и evidence pointers"); app.innerHTML = renderKnowledgeDetail(data); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "monitoring") {
      const integration = await api.monitoring(current.project);
      const data = { ...overviewCache, integration_monitoring: integration };
      renderChanged(current, data, () => {
        setPage("Мониторинг", current.project ? "Техническое состояние выбранного проекта и глобального runtime" : "Core, PostgreSQL, MCP и IDE-интеграции");
        app.innerHTML = renderMonitoring(data, current);
      });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "activity") {
      const data = await api.activity({
        project_key: current.project,
        mode: current.mode || "milestones",
        occurred_after: current.occurredAfter,
        occurred_before: current.occurredBefore,
        work_id: current.workId,
        task_id: current.taskId,
        epic_id: current.epicId,
        actor_id: current.actorId,
        event_type: current.eventType,
        status: current.status,
        importance: current.importance,
        assurance: current.assurance,
        cursor: current.cursor,
        limit: 25,
      });
      renderChanged(current, data, () => { setPage("История", current.project ? "Milestones и результаты выбранного проекта" : "Durable milestone-first журнал по всем проектам"); app.innerHTML = renderActivity(data, current); });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else {
      renderChanged(current, overviewCache, () => {
        setPage("Обзор", "Проекты, текущая работа, недавние результаты и то, что требует внимания");
        app.innerHTML = renderOverview(overviewCache);
      });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    }

    if (!keepCurrentRoute(current)) return;
    clearRefreshWarning();
    updatedAt.textContent = `обновлено ${time(generatedAt)}`;
    const background = Boolean(overviewCache.service?.background);
    setConnection(true, background ? "Система активна" : "AI Layer активен");
    sidebarVersion.textContent = `AI Layer ${overviewCache.version || ""}`.trim();
  } catch (error) {
    if (!routeIsCurrent(current)) {
      reloadRequested = true;
      return;
    }
    setConnection(false, "Обновление недоступно");
    showRefreshWarning(error);
    nextPollMs = IDLE_POLL_MS;
  }
}

async function load() {
  if (loadPromise) {
    reloadRequested = true;
    await loadPromise;
    return;
  }
  loadPromise = (async () => {
    do {
      reloadRequested = false;
      await loadCycle();
    } while (reloadRequested);
  })();
  try {
    await loadPromise;
  } finally {
    loadPromise = null;
  }
}

function schedule() {
  if (timer) clearTimeout(timer);
  timer = null;
  if (document.hidden) return;
  timer = setTimeout(async () => { await load(); schedule(); }, nextPollMs);
}

async function refresh({ resetOverview = false } = {}) {
  if (resetOverview) {
    overviewCache = null;
    overviewCachedAt = 0;
    projectCockpitCache.clear();
  }
  await load();
  schedule();
}

window.addEventListener("hashchange", () => {
  lastRenderFingerprint = null;
  setNavigationBusy(true);
  void refresh().finally(() => setNavigationBusy(false));
});
refreshButton.addEventListener("click", () => {
  setNavigationBusy(true);
  void refresh({ resetOverview: true }).finally(() => setNavigationBusy(false));
});
projectScope.addEventListener("change", () => navigateScope(projectScope.value || null));
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (timer) clearTimeout(timer);
    timer = null;
    return;
  }
  void refresh({ resetOverview: true });
});

setNavigationBusy(true);
void refresh().finally(() => setNavigationBusy(false));
