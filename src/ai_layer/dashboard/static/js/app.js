import { api } from "./api.js";
import { time, escapeHtml } from "./format.js";
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
  const [kind, key] = value.split("/");
  return kind === "project" && key ? { kind: "project", key: decodeURIComponent(key) } : { kind: "overview" };
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
  else document.querySelector(`[data-project-nav="${CSS.escape(current.key)}"]`)?.classList.add("active");
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
    if (!overviewCache || route().kind === "overview") overviewCache = await api.overview();
    renderNav(overviewCache);
    const current = route();
    if (current.kind === "project") {
      const data = await api.project(current.key);
      pageTitle.textContent = data.project?.name || "Проект";
      pageSubtitle.textContent = "Задача, стадии, ревью и состояние проекта";
      app.innerHTML = renderProject(data);
      updatedAt.textContent = `обновлено ${time(data.generated_at)}`;
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
