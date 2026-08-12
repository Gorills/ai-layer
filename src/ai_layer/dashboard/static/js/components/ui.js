import { escapeHtml } from "../format.js";

export function hashUrl(path, params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== ""),
  ).toString();
  return `#/${path}${query ? `?${query}` : ""}`;
}

export function pagination(paginationData, path, params = {}) {
  const p = paginationData || {};
  if (!p.pages || p.pages <= 1) return "";
  const current = Number(p.page || 1);
  const pages = Number(p.pages || 1);
  const previous = current > 1 ? current - 1 : null;
  const next = current < pages ? current + 1 : null;
  const visible = [];
  for (let value = Math.max(1, current - 2); value <= Math.min(pages, current + 2); value += 1) {
    visible.push(value);
  }
  return `<nav class="pagination" aria-label="Пагинация">
    ${previous ? `<a class="page-button" href="${hashUrl(path, { ...params, page: previous })}">←</a>` : `<span class="page-button disabled">←</span>`}
    ${visible[0] > 1 ? `<a class="page-button" href="${hashUrl(path, { ...params, page: 1 })}">1</a>${visible[0] > 2 ? `<span class="page-gap">…</span>` : ""}` : ""}
    ${visible.map((value) => `<a class="page-button ${value === current ? "active" : ""}" href="${hashUrl(path, { ...params, page: value })}">${escapeHtml(value)}</a>`).join("")}
    ${visible[visible.length - 1] < pages ? `${visible[visible.length - 1] < pages - 1 ? `<span class="page-gap">…</span>` : ""}<a class="page-button" href="${hashUrl(path, { ...params, page: pages })}">${escapeHtml(pages)}</a>` : ""}
    ${next ? `<a class="page-button" href="${hashUrl(path, { ...params, page: next })}">→</a>` : `<span class="page-button disabled">→</span>`}
  </nav>`;
}

export function projectPicker(projects, selected, path, params = {}, { allowAll = true } = {}) {
  const options = [];
  if (allowAll) {
    options.push(`<option value="${hashUrl(path, { ...params, project: null, page: null })}" ${!selected ? "selected" : ""}>Все проекты</option>`);
  }
  for (const project of projects || []) {
    options.push(`<option value="${hashUrl(path, { ...params, project: project.key, page: null })}" ${project.key === selected ? "selected" : ""}>${escapeHtml(project.name)}</option>`);
  }
  return `<label class="filter-control"><span>Проект</span><select data-hash-select>${options.join("")}</select></label>`;
}

export function filterTabs(items, active, path, params = {}, key = "status") {
  return `<div class="filter-tabs">${items.map((item) => {
    const isActive = String(item.value ?? "") === String(active ?? "");
    return `<a class="filter-tab ${isActive ? "active" : ""}" href="${hashUrl(path, { ...params, [key]: item.value || null, page: null })}">${escapeHtml(item.label)}</a>`;
  }).join("")}</div>`;
}

function inline(text) {
  return escapeHtml(text || "")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

export function markdown(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let list = null;
  let code = false;
  const closeList = () => {
    if (!list) return;
    out.push(`</${list}>`);
    list = null;
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().startsWith("```")) {
      closeList();
      code = !code;
      out.push(code ? `<pre class="content-code"><code>` : "</code></pre>");
      continue;
    }
    if (code) {
      out.push(`${escapeHtml(raw)}\n`);
      continue;
    }
    if (!line.trim()) {
      closeList();
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(5, heading[1].length + 1);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (list !== "ul") {
        closeList();
        list = "ul";
        out.push("<ul>");
      }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    const ordered = line.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      if (list !== "ol") {
        closeList();
        list = "ol";
        out.push("<ol>");
      }
      out.push(`<li>${inline(ordered[1])}</li>`);
      continue;
    }
    closeList();
    out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  if (code) out.push("</code></pre>");
  return out.join("");
}

export function compactList(items, emptyLabel = "Нет данных") {
  if (!items?.length) return `<div class="empty compact">${escapeHtml(emptyLabel)}</div>`;
  return `<ul class="compact-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

export function infoRow(label, value, note = "") {
  return `<div class="info-row"><div><div class="info-label">${escapeHtml(label)}</div>${note ? `<div class="info-note">${escapeHtml(note)}</div>` : ""}</div><div class="info-value">${escapeHtml(value ?? "—")}</div></div>`;
}
