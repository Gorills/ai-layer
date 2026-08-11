import { api } from "./api.js";
import { time, escapeHtml } from "./format.js";
import { renderEpicDetail, renderEpicList } from "./views/epic.js";
import { renderOverview } from "./views/overview.js";
import { renderProject } from "./views/project.js";
import { renderActivity, renderMonitoring, renderTaskDetail, renderTasks } from "./views/operations.js";
import { renderKnowledge, renderKnowledgeDetail, renderRules, renderSkillDetail, renderSkills } from "./views/reference.js";

const app = document.querySelector("#app");
const projectNav = document.querySelector("#project-nav");
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

let overviewCache = null;
let timer = null;
let loading = false;
let nextPollMs = IDLE_POLL_MS;
let lastRenderFingerprint = null;
let lastNavFingerprint = null;

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
  };
  if (parts[0] === "project" && parts[1]) return { kind: "project", key: decodeURIComponent(parts[1]), ...common };
  if (parts[0] === "epic" && parts[1] && parts[2]) return { kind: "epic", projectKey: decodeURIComponent(parts[1]), epicKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "task" && parts[1] && parts[2]) return { kind: "task", projectKey: decodeURIComponent(parts[1]), taskKey: decodeURIComponent(parts[2]), ...common };
  if (parts[0] === "skill" && parts[1]) return { kind: "skill", slug: decodeURIComponent(parts[1]), ...common };
  if (parts[0] === "knowledge-card" && parts[1] && parts[2]) return { kind: "knowledge-card", projectKey: decodeURIComponent(parts[1]), knowledgeId: decodeURIComponent(parts[2]), ...common };
  if (["tasks", "skills", "rules", "knowledge", "monitoring", "activity"].includes(parts[0])) return { kind: parts[0], ...common };
  return { kind: "overview", ...common };
}

function routeKey(current) {
  return JSON.stringify(current);
}

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
  if (["skill", "skills"].includes(kind)) return "skills";
  if (["knowledge", "knowledge-card"].includes(kind)) return "knowledge";
  return kind;
}

function renderNav(data) {
  const projects = data.projects || [];
  const fingerprint = JSON.stringify(projects.map((project) => [project.key, project.name]));
  if (fingerprint !== lastNavFingerprint) {
    projectNav.innerHTML = projects.map((project) => `<a class="nav-item project-link" href="#/project/${encodeURIComponent(project.key)}" data-project-nav="${escapeHtml(project.key)}"><span class="nav-project-dot"></span><span>${escapeHtml(project.name)}</span></a>`).join("");
    lastNavFingerprint = fingerprint;
  }
  const current = route();
  document.querySelectorAll(".nav-item.active").forEach((element) => element.classList.remove("active"));
  document.querySelector(`[data-route="${CSS.escape(rootRoute(current.kind))}"]`)?.classList.add("active");
  const projectKey = current.kind === "project" ? current.key : current.kind === "epic" || current.kind === "task" ? current.projectKey : current.project;
  if (projectKey) document.querySelector(`[data-project-nav="${CSS.escape(projectKey)}"]`)?.classList.add("active");
}

function bindDynamicControls() {
  document.querySelectorAll("[data-project-key]").forEach((row) => row.addEventListener("click", () => { location.hash = `#/project/${encodeURIComponent(row.dataset.projectKey)}`; }));
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

function epicIsLive(data) {
  return ["running", "final_review"].includes(data?.epic?.status || "");
}

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
      const [data, epicData] = await Promise.all([api.project(current.key), api.projectEpics(current.key)]);
      renderChanged(current, { data, epicData }, () => {
        setPage(data.project?.name || "Проект", "Задача, workflow, знания и локальные runtime-сигналы");
        app.innerHTML = `${renderProject(data)}${renderEpicList(epicData, current.key)}`;
      });
      generatedAt = data.generated_at;
      nextPollMs = projectIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "epic") {
      const data = await api.epic(current.projectKey, current.epicKey);
      renderChanged(current, data, () => {
        setPage(`${data.epic?.key || "Epic"} · ${data.epic?.title || ""}`, "Specification · audits · Phase 0 · Task plan · final review");
        app.innerHTML = renderEpicDetail(data);
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
      renderChanged(current, overviewCache, () => { setPage("Мониторинг", "Core, PostgreSQL, MCP, memory и локальные процессы"); app.innerHTML = renderMonitoring(overviewCache); });
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "activity") {
      const data = await api.activity({ project_key: current.project, page: current.page, page_size: 10 });
      renderChanged(current, data, () => { setPage("Активность", "Компактный журнал технических операций"); app.innerHTML = renderActivity(data, current); });
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
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (timer) clearTimeout(timer);
    timer = null;
    return;
  }
  void refresh({ resetOverview: true });
});

void refresh();
