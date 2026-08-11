const base = "/api/v1/dashboard";

async function request(path) {
  const response = await fetch(`${base}${path}`, { headers: { "Accept": "application/json" }, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text || response.statusText}`);
  }
  return response.json();
}

export const api = {
  overview: () => request("/overview"),
  project: (key) => request(`/projects/${encodeURIComponent(key)}`),
};
