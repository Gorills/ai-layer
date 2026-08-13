import { api } from "./api.js";
import { hashUrl } from "./components/ui.js";
import { time, escapeHtml } from "./format.js";
import { renderEpicDetail, renderEpics } from "./views/epic.js";
import { renderOverview } from "./views/overview.js";
import { renderProject } from "./views/project.js";
import { renderActivity, renderMonitoring, renderTaskDetail, renderTasks } from "./views/operations.js";
import { renderKnowledge, renderKnowledgeDetail, renderRules, renderSkillDetail, renderSkills } from "./views/reference.js";

const app = document.querySelector("#app");
const projectScope = document.querySelector("#project-scope");
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
const FILTERABLE_ROOTS = new Set(["tasks", "epics", "skills", "rules", "knowledge", "monitoring", "activity"]);

let overviewCache = null;
let timer = null;
let loading = false;
let nextPollMs = IDLE_POLL_MS;
let lastRenderFingerprint = null;
let lastScopeFingerprint = null;

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
  if (parts[0] === "project" && parts[1]) return { kind: "project", key: decodeURIComponent(parts[1]), ...common };
  if (parts[0] === "epic" && parts[1] && parts[2]) return { kind: "epic", projectKey: decodeURIComponent(parts[1]), epicKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "task" && parts[1] && parts[2]) return { kind: "task", projectKey: decodeURIComponent(parts[1]), taskKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "skill" && parts[1]) return { kind: "skill", slug: decodeURIComponent(parts[1]), ...common };
  if (parts[0] === "knowledge-card" && parts[1] && parts[2]) return { kind: "knowledge-card", projectKey: decodeURIComponent(parts[1]), knowledgeId: decodeURIComponent(parts[2]), ...common };
  if (["tasks", "epics", "skills", "rules", "knowledge", "monitoring", "activity"].includes(parts[0])) return { kind: parts[0], ...common };
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

function rootRoute(kind) {
  if (["task", "tasks"].includes(kind)) return "tasks";
  if (["epic", "epics"].includes(kind)) return "epics";
  if (["skill", "skills"].includes(kind)) return "skills";
  if (["knowledge", "knowledge-card"].includes(kind)) return "knowledge";
  if (kind === "project") return "overview";
  return kind;
}

function projectForRoute(current) {
  if (current.kind === "project") return current.key;
  if (["epic", "task", "knowledge-card"].includes(current.kind)) return current.projectKey;
  return current.project || null;
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
  projectScope.value = projects.some((project) => project.key === selectedProject) ? selectedProject : "";
  document.querySelectorAll(".nav-item.active").forEach((element) => element.classList.remove("active"));
  document.querySelector(`[data-route="${CSS.escape(rootRoute(current.kind))}"]`)?.classList.add("active");
  document.body.dataset.route = rootRoute(current.kind);
}

function navigateScope(projectKey) {
  const current = route();
  const root = rootRoute(current.kind);
  if (current.kind === "overview" || current.kind === "project") {
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
}

function overviewIsLive(data) {
  const summary = data?.summary || {};
  return Number(summary.active_tasks || 0) > 0 || Number(summary.active_agents || 0) > 0;
}

function projectIsLive(data) {
  const project = data?.project || {};
  const task = data?.task_state?.current || {};
  return project.runtime_state === "active" || project.project_state === "working" || task.status === "active" || (project.active_operations || []).length > 0;
}

function epicIsLive(data) { return ["phase0", "planning", "running", "final_review"].includes(data?.epic?.status || ""); }
function epicsAreLive(data) { return (data?.items || []).some((item) => ["phase0", "planning", "running", "final_review"].includes(item.status || "")); }

function renderChanged(current, payload, render) {
  const fingerprint = semanticFingerprint(current, payload);
  if (fingerprint === lastRenderFingerprint) return false;
  lastRenderFingerprint = fingerprint;
  render();
  bindDynamicControls();
  return true;
}

function setPage(title, subtitle) {
  pageTitle.textContent = title;
  pageSubtitle.textContent = subtitle;
}

async function load() {
  if (loading) return;
  loading = true;
  try {
    const current = route();
    if (!overviewCache || current.kind === "overview" || current.kind === "monitoring") overviewCache = await api.overview();
    renderNav(overviewCache);

    let generatedAt = overviewCache.generated_at;
    if (current.kind === "project") {
      const data = await api.project(current.key);
      renderChanged(current, data, () => {
        setPage(data.project?.name || "Проект", "Workflow, runtime, memory и наблюдаемые сигналы");
        app.innerHTML = renderProject(data);
      });
      generatedAt = data.generated_at;
      nextPollMs = projectIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "epics") {
      const data = await api.epics({ project_key: current.project, status: current.status, page: current.page, page_size: 10 });
      renderChanged(current, data, () => {
        setPage("Эпики", "Крупные инициативы, спецификации и прогресс последовательных Task");
        app.innerHTML = renderEpics(data, current);
      });
      generatedAt = data.generated_at || overviewCache.generated_at;
      nextPollMs = epicsAreLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "epic") {
      const data = await api.epic(current.projectKey, current.epicKey);
      renderChanged(current, data, () => {
        setPage(`${data.epic?.key || "Epic"} · ${data.epic?.title || ""}`, "Specification · Tasks · audits · final review");
        app.innerHTML = renderEpicDetail(data, current);
      });
      generatedAt = data.epic?.updated_at;
      nextPollMs = epicIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "tasks") {
      const data = await api.tasks({ project_key: current.project, status: current.status, page: current.page, page_size: 10 });
      renderChanged(current, data, () => { setPage("Задачи", "Текущая работа и полная история Task"); app.innerHTML = renderTasks(data, current); });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "task") {
      const data = await api.task(current.projectKey, current.taskKey);
      renderChanged(current, data, () => { setPage(`${data.task?.key || "Task"}`, "Стадии, review findings, verification и model assurance"); app.innerHTML = renderTaskDetail(data); });
      nextPollMs = data.task?.status === "active" ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "skills") {
      const data = await api.skills({ project_key: current.project, page: current.page, page_size: 10 });
      renderChanged(current, data, () => { setPage("Скиллы", "Краткий каталог и полный локальный контент"); app.innerHTML = renderSkills(data, current); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "skill") {
      const data = await api.skill(current.slug, current.project);
      renderChanged(current, data, () => { setPage(data.slug || "Skill", "Краткий core или полный skill"); app.innerHTML = renderSkillDetail(data, current); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "rules") {
      const data = await api.rules(current.project);
      renderChanged(current, data, () => { setPage("Правила", "Глобальная policy, project rules и privacy constraints"); app.innerHTML = renderRules(data, current); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "knowledge") {
      const projectKey = current.project || overviewCache.projects?.[0]?.key;
      if (!projectKey) throw new Error("Нет зарегистрированных проектов для базы знаний");
      const data = await api.knowledge(projectKey, { status: current.status || "VERIFIED", page: current.page, page_size: 10 });
      const effective = { ...current, project: projectKey };
      renderChanged(effective, data, () => { setPage("База знаний", "Verified Project Knowledge и review-gated drafts"); app.innerHTML = renderKnowledge(data, effective); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "knowledge-card") {
      const data = await api.knowledgeDetail(current.projectKey, current.knowledgeId);
      renderChanged(current, data, () => { setPage(data.card?.title || "Knowledge", "Claims, constraints, unknowns и evidence pointers"); app.innerHTML = renderKnowledgeDetail(data); });
      nextPollMs = IDLE_POLL_MS;
    } else if (current.kind === "monitoring") {
      const integration = await api.monitoring(current.project);
      const data = { ...overviewCache, integration_monitoring: integration };
      renderChanged(current, data, () => {
        setPage("Мониторинг", "Core, PostgreSQL, MCP, memory и IDE-интеграции");
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
      renderChanged(current, data, () => { setPage("Активность", "Durable milestone-first журнал работы"); app.innerHTML = renderActivity(data, current); });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else {
      renderChanged(current, overviewCache, () => {
        setPage("Обзор системы", "Текущее состояние AI Layer и локальных сервисов");
        app.innerHTML = renderOverview(overviewCache);
      });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    }

    updatedAt.textContent = `обновлено ${time(generatedAt)}`;
    const background = Boolean(overviewCache.service?.background);
    setConnection(true, background ? "Система активна" : "AI Layer активен");
    sidebarVersion.textContent = `AI Layer ${overviewCache.version || ""}`.trim();
  } catch (error) {
    setConnection(false, "Панель отключена");
    lastRenderFingerprint = null;
    app.innerHTML = `<div class="alert">Ошибка API панели: ${escapeHtml(error.message)}</div>`;
    nextPollMs = IDLE_POLL_MS;
  } finally {
    loading = false;
  }
}

function schedule() {
  if (timer) clearTimeout(timer);
  timer = null;
  if (document.hidden) return;
  timer = setTimeout(async () => { await load(); schedule(); }, nextPollMs);
}

async function refresh({ resetOverview = false } = {}) {
  if (resetOverview) overviewCache = null;
  await load();
  schedule();
}

window.addEventListener("hashchange", () => { lastRenderFingerprint = null; void refresh({ resetOverview: true }); });
refreshButton.addEventListener("click", () => { void refresh({ resetOverview: true }); });
projectScope.addEventListener("change", () => navigateScope(projectScope.value || null));
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (timer) clearTimeout(timer);
    timer = null;
    return;
  }
  void refresh({ resetOverview: true });
});

void refresh();
