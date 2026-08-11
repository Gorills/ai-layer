import { api } from "./api.js";
import { time, escapeHtml } from "./format.js";
import { renderEpicDetail, renderEpicList } from "./views/epic.js";
import { renderOverview } from "./views/overview.js";
import { renderProject } from "./views/project.js";

const app = document.querySelector("#app");
const projectNav = document.querySelector("#project-nav");
const pageTitle = document.querySelector("#page-title");
const pageSubtitle = document.querySelector("#page-subtitle");
const updatedAt = document.querySelector("#updated-at");
const dot = document.querySelector("#connection-dot");
const connectionLabel = document.querySelector("#connection-label");
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

function route() {
  const value = location.hash.replace(/^#\/?/, "") || "overview";
  const parts = value.split("/");
  if (parts[0] === "project" && parts[1]) {
    return { kind: "project", key: decodeURIComponent(parts[1]) };
  }
  if (parts[0] === "epic" && parts[1] && parts[2]) {
    return {
      kind: "epic",
      projectKey: decodeURIComponent(parts[1]),
      epicKey: decodeURIComponent(parts[2]),
    };
  }
  return { kind: "overview" };
}

function routeKey(current) {
  if (current.kind === "project") return `project:${current.key}`;
  if (current.kind === "epic") return `epic:${current.projectKey}:${current.epicKey}`;
  return "overview";
}

function semanticFingerprint(current, payload) {
  return JSON.stringify([routeKey(current), payload], (key, value) => (
    VOLATILE_RENDER_FIELDS.has(key) ? undefined : value
  ));
}

function setConnection(ok, label) {
  dot.classList.toggle("online", ok);
  dot.classList.toggle("offline", !ok);
  connectionLabel.textContent = label;
}

function renderNav(data) {
  const projects = data.projects || [];
  const fingerprint = JSON.stringify(projects.map((p) => [p.key, p.name]));
  if (fingerprint !== lastNavFingerprint) {
    projectNav.innerHTML = projects.map((p) => `<a class="nav-item" href="#/project/${encodeURIComponent(p.key)}" data-project-nav="${escapeHtml(p.key)}">${escapeHtml(p.name)}</a>`).join("");
    lastNavFingerprint = fingerprint;
  }
  const current = route();
  document.querySelectorAll(".nav-item.active").forEach((el) => el.classList.remove("active"));
  if (current.kind === "overview") document.querySelector('[data-route="overview"]')?.classList.add("active");
  else {
    const key = current.kind === "epic" ? current.projectKey : current.key;
    document.querySelector(`[data-project-nav="${CSS.escape(key)}"]`)?.classList.add("active");
  }
}

function bindProjectRows() {
  document.querySelectorAll("[data-project-key]").forEach((row) => {
    row.addEventListener("click", () => { location.hash = `#/project/${encodeURIComponent(row.dataset.projectKey)}`; });
  });
}

function overviewIsLive(data) {
  const summary = data?.summary || {};
  return Number(summary.active_tasks || 0) > 0 || Number(summary.active_agents || 0) > 0;
}

function projectIsLive(data) {
  const project = data?.project || {};
  const task = data?.task_state?.current || {};
  return project.runtime_state === "active"
    || project.project_state === "working"
    || task.status === "active"
    || (project.active_operations || []).length > 0;
}

function epicIsLive(data) {
  return ["running", "final_review"].includes(data?.epic?.status || "");
}

function renderChanged(current, payload, render) {
  const fingerprint = semanticFingerprint(current, payload);
  if (fingerprint === lastRenderFingerprint) return false;
  lastRenderFingerprint = fingerprint;
  render();
  return true;
}

async function load() {
  if (loading) return;
  loading = true;
  try {
    const current = route();
    if (!overviewCache || current.kind === "overview") overviewCache = await api.overview();
    renderNav(overviewCache);
    if (current.kind === "project") {
      const [data, epicData] = await Promise.all([api.project(current.key), api.projectEpics(current.key)]);
      renderChanged(current, { data, epicData }, () => {
        pageTitle.textContent = data.project?.name || "Проект";
        pageSubtitle.textContent = "Задачи, Epics, стадии, ревью и состояние проекта";
        app.innerHTML = `${renderProject(data)}${renderEpicList(epicData, current.key)}`;
      });
      updatedAt.textContent = `обновлено ${time(data.generated_at)}`;
      nextPollMs = projectIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else if (current.kind === "epic") {
      const data = await api.epic(current.projectKey, current.epicKey);
      renderChanged(current, data, () => {
        pageTitle.textContent = `${data.epic?.key || "Epic"} · ${data.epic?.title || ""}`;
        pageSubtitle.textContent = "Specification · audits · Phase 0 · Task plan · final review";
        app.innerHTML = renderEpicDetail(data);
      });
      updatedAt.textContent = `обновлено ${time(data.epic?.updated_at)}`;
      nextPollMs = epicIsLive(data) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    } else {
      renderChanged(current, overviewCache, () => {
        pageTitle.textContent = "Обзор";
        pageSubtitle.textContent = "Текущие задачи, стадии и состояние AI Layer";
        app.innerHTML = renderOverview(overviewCache);
        bindProjectRows();
      });
      updatedAt.textContent = `обновлено ${time(overviewCache.generated_at)}`;
      nextPollMs = overviewIsLive(overviewCache) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    }
    const background = Boolean(overviewCache.service?.background);
    setConnection(true, `${background ? "Фоновая служба" : "AI Layer"} ${overviewCache.version || ""}`.trim());
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
  timer = setTimeout(async () => {
    await load();
    schedule();
  }, nextPollMs);
}

async function refresh({ resetOverview = false } = {}) {
  if (resetOverview) overviewCache = null;
  await load();
  schedule();
}

window.addEventListener("hashchange", () => {
  lastRenderFingerprint = null;
  void refresh({ resetOverview: true });
});
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
