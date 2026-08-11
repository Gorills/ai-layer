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

let overviewCache = null;
let timer = null;
let loading = false;

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

function setConnection(ok, label) {
  dot.classList.toggle("online", ok);
  dot.classList.toggle("offline", !ok);
  connectionLabel.textContent = label;
}

function renderNav(data) {
  projectNav.innerHTML = (data.projects || []).map((p) => `<a class="nav-item" href="#/project/${encodeURIComponent(p.key)}" data-project-nav="${escapeHtml(p.key)}">${escapeHtml(p.name)}</a>`).join("");
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

async function load() {
  if (loading) return;
  loading = true;
  try {
    const current = route();
    if (!overviewCache || current.kind === "overview") overviewCache = await api.overview();
    renderNav(overviewCache);
    if (current.kind === "project") {
      const [data, epicData] = await Promise.all([api.project(current.key), api.projectEpics(current.key)]);
      pageTitle.textContent = data.project?.name || "Проект";
      pageSubtitle.textContent = "Задачи, Epics, стадии, ревью и состояние проекта";
      app.innerHTML = `${renderProject(data)}${renderEpicList(epicData, current.key)}`;
      updatedAt.textContent = `обновлено ${time(data.generated_at)}`;
    } else if (current.kind === "epic") {
      const data = await api.epic(current.projectKey, current.epicKey);
      pageTitle.textContent = `${data.epic?.key || "Epic"} · ${data.epic?.title || ""}`;
      pageSubtitle.textContent = "Specification · audits · Phase 0 · Task plan · final review";
      app.innerHTML = renderEpicDetail(data);
      updatedAt.textContent = `обновлено ${time(data.epic?.updated_at)}`;
    } else {
      pageTitle.textContent = "Обзор";
      pageSubtitle.textContent = "Текущие задачи, стадии и состояние AI Layer";
      app.innerHTML = renderOverview(overviewCache);
      updatedAt.textContent = `обновлено ${time(overviewCache.generated_at)}`;
      bindProjectRows();
    }
    const background = Boolean(overviewCache.service?.background);
    setConnection(true, `${background ? "Фоновая служба" : "AI Layer"} ${overviewCache.version || ""}`.trim());
  } catch (error) {
    setConnection(false, "Панель отключена");
    app.innerHTML = `<div class="alert">Ошибка API панели: ${escapeHtml(error.message)}</div>`;
  } finally {
    loading = false;
  }
}

function schedule() {
  if (timer) clearInterval(timer);
  timer = setInterval(load, 2000);
}

window.addEventListener("hashchange", () => { overviewCache = null; load(); });
refreshButton.addEventListener("click", () => { overviewCache = null; load(); });
load();
schedule();