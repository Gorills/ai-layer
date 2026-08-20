const base = "/api/v1/dashboard";
const REQUEST_TIMEOUT_MS = 10000;

async function request(path, params = null) {
  const query = params
    ? `?${new URLSearchParams(Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== "")).toString()}`
    : "";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${base}${path}${query}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${response.status}: ${text || response.statusText}`);
    }
    return response.json();
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("Таймаут обновления Dashboard");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  overview: () => request("/overview"),
  work: (params = {}) => request("/work", params),
  workDetail: (projectKey, workKey) => request(`/work/${encodeURIComponent(projectKey)}/${encodeURIComponent(workKey)}`),
  tasks: (params = {}) => request("/tasks", params),
  task: (projectKey, taskKey) => request(`/tasks/${encodeURIComponent(projectKey)}/${encodeURIComponent(taskKey)}`),
  epics: (params = {}) => request("/epics", params),
  skills: (params = {}) => request("/skills", params),
  skill: (slug, projectKey = null) => request(`/skills/${encodeURIComponent(slug)}`, { project_key: projectKey }),
  rules: (projectKey = null) => request("/rules", { project_key: projectKey }),
  knowledge: (projectKey, params = {}) => request(`/knowledge/${encodeURIComponent(projectKey)}`, params),
  knowledgeDetail: (projectKey, knowledgeId) => request(`/knowledge/${encodeURIComponent(projectKey)}/${encodeURIComponent(knowledgeId)}`),
  monitoring: (projectKey = null) => request("/monitoring", { project_key: projectKey }),
  activity: (params = {}) => request("/activity", params),
  project: (key) => request(`/projects/${encodeURIComponent(key)}`),
  projectEpics: (key) => request(`/projects/${encodeURIComponent(key)}/epics`),
  epic: (projectKey, epicKey) => request(`/projects/${encodeURIComponent(projectKey)}/epics/${encodeURIComponent(epicKey)}`),
};
