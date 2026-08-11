from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from ai_layer.memory.source import read_text, redact_secrets

CSS_VAR_RE = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;{}]{1,120})")
HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;{}]{1,160})", re.I)
RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;{}]{1,80})", re.I)
SPACING_RE = re.compile(r"(?:gap|padding|margin)(?:-[a-z-]+)?\s*:\s*([^;{}]{1,80})", re.I)
SEO_MARKERS = {
    "title": re.compile(r"<title\b|document\.title|metadata\s*=", re.I),
    "description": re.compile(r"meta[^>]+name=[\"']description|description\s*:", re.I),
    "canonical": re.compile(r"rel=[\"']canonical|canonical\s*:", re.I),
    "structured_data": re.compile(r"application/ld\+json|schema\.org|jsonld", re.I),
    "robots_meta": re.compile(r"name=[\"']robots|robots\s*:", re.I),
}


def _paths(rows: Iterable[object]) -> list[str]:
    return [str(getattr(row, "path", "")) for row in rows if bool(getattr(row, "indexed", True))]


def _dep_text(dependencies: dict[str, list[str]]) -> str:
    return " ".join(str(item) for values in dependencies.values() for item in values).casefold()


def _read_json(root: Path, rel: str) -> dict:
    text = read_text(root / rel)
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def frontend_topology(root: Path, rows: Iterable[object], dependencies: dict[str, list[str]]) -> dict:
    paths = _paths(rows)
    dep_text = _dep_text(dependencies)
    frameworks: list[str] = []
    framework_hints = {
        "react": ("react@", "react ", "next@", "next "),
        "vue": ("vue@", "vue ", "nuxt@", "nuxt "),
        "svelte": ("svelte@", "svelte ", "@sveltejs"),
    }
    for framework, hints in framework_hints.items():
        if any(hint in dep_text for hint in hints):
            frameworks.append(framework)
    styling = [
        name for name in ("tailwind", "bootstrap", "sass", "styled-components", "emotion", "mui", "chakra", "vuetify")
        if name in dep_text
    ]
    state = [
        name for name in ("redux", "zustand", "mobx", "pinia", "vuex", "xstate", "tanstack", "react-query")
        if name in dep_text
    ]
    e2e = [name for name in ("playwright", "cypress", "selenium") if name in dep_text]
    component_roots = sorted({
        "/".join(Path(p).parts[:2]) for p in paths
        if any(part.casefold() in {"components", "views", "pages", "routes", "screens"} for part in Path(p).parts[:-1])
    })[:30]
    route_files = sorted(
        p for p in paths
        if Path(p).name.casefold() in {"router.ts", "router.js", "routes.ts", "routes.js", "app-router.tsx", "app.tsx"}
        or any(part.casefold() in {"pages", "routes", "app"} for part in Path(p).parts[:-1]) and Path(p).suffix.casefold() in {".tsx", ".jsx", ".vue", ".svelte"}
    )[:40]
    return {
        "present": bool(frameworks or any(Path(p).suffix.casefold() in {".html", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"} for p in paths)),
        "frameworks": frameworks,
        "styling": styling,
        "state_management": state,
        "e2e_tools": e2e,
        "component_roots": component_roots,
        "route_evidence": route_files,
    }


def design_profile(root: Path, rows: Iterable[object], dependencies: dict[str, list[str]], frontend: dict) -> dict:
    paths = _paths(rows)
    preferred = [
        p for p in paths
        if Path(p).suffix.casefold() in {".css", ".scss", ".sass", ".less"}
        and any(hint in p.casefold() for hint in ("theme", "token", "variable", "style", "global", "app", "base"))
    ]
    fallback = [p for p in paths if Path(p).suffix.casefold() in {".css", ".scss", ".sass", ".less"}]
    css_files = list(dict.fromkeys(preferred + fallback))[:36]
    custom_properties: dict[str, str] = {}
    colors: list[str] = []
    fonts: list[str] = []
    radii: list[str] = []
    spacing: list[str] = []
    evidence_files: list[str] = []
    for rel in css_files:
        text = read_text(root / rel)
        if not text:
            continue
        evidence_files.append(rel)
        for key, value in CSS_VAR_RE.findall(text):
            if len(custom_properties) >= 60:
                break
            custom_properties.setdefault(key, redact_secrets(value.strip()))
        colors.extend(HEX_COLOR_RE.findall(text)[:40])
        fonts.extend(value.strip() for value in FONT_FAMILY_RE.findall(text)[:10])
        radii.extend(value.strip() for value in RADIUS_RE.findall(text)[:20])
        spacing.extend(value.strip() for value in SPACING_RE.findall(text)[:30])
    dep_text = _dep_text(dependencies)
    component_libraries = [
        name for name in ("mui", "material-ui", "bootstrap", "chakra", "vuetify", "antd", "ant-design", "radix", "headlessui")
        if name in dep_text
    ]
    token_signal = bool(custom_properties) or any("tailwind" in item for item in frontend.get("styling", []))
    return {
        "evidence_files": evidence_files[:24],
        "css_custom_properties": dict(list(custom_properties.items())[:40]),
        "colors": sorted(set(colors))[:20],
        "font_families": sorted(set(fonts))[:12],
        "border_radii": sorted(set(radii))[:12],
        "spacing_values": sorted(set(spacing))[:20],
        "component_libraries": sorted(set(component_libraries)),
        "design_system_signal": "explicit_tokens" if token_signal else "conventions_only_or_unknown",
        "note": "Observed visual-language evidence only; values are not a judgment of design quality.",
    }


def seo_profile(root: Path, rows: Iterable[object], dependencies: dict[str, list[str]], frontend: dict) -> dict:
    paths = _paths(rows)
    dep_text = _dep_text(dependencies)
    robots = sorted(p for p in paths if Path(p).name.casefold() == "robots.txt")[:10]
    sitemaps = sorted(p for p in paths if "sitemap" in Path(p).name.casefold())[:20]
    ssr = [name for name in ("next", "nuxt", "@sveltejs/kit", "astro") if name in dep_text]
    marker_paths: dict[str, list[str]] = {key: [] for key in SEO_MARKERS}
    candidates = [
        p for p in paths
        if Path(p).suffix.casefold() in {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".js", ".ts", ".php", ".py"}
        and not any(part.casefold() in {"tests", "test", "spec", "specs", "__tests__"} for part in Path(p).parts)
    ][:120]
    for rel in candidates:
        text = read_text(root / rel)
        if not text:
            continue
        sample = text[:120_000]
        for key, pattern in SEO_MARKERS.items():
            if pattern.search(sample) and len(marker_paths[key]) < 12:
                marker_paths[key].append(rel)
    public_surface = bool(frontend.get("present") and (robots or sitemaps or any(marker_paths.values()) or ssr))
    return {
        "public_web_surface": public_surface,
        "robots_files": robots,
        "sitemap_files": sitemaps,
        "ssr_or_prerender_frameworks": ssr,
        "marker_evidence": {key: values for key, values in marker_paths.items() if values},
        "note": "Presence evidence only; scanner does not claim pages are indexable, canonicalized, or ranking well.",
    }


def documentation_profile(root: Path, rows: Iterable[object]) -> dict:
    paths = _paths(rows)
    docs = sorted(
        p for p in paths
        if Path(p).suffix.casefold() in {".md", ".rst", ".txt"}
        and (
            p.casefold().startswith("docs/")
            or Path(p).name.casefold().startswith(("readme", "changelog", "contributing", "deploy", "runbook", "architecture"))
        )
    )[:120]
    env_examples = sorted(p for p in paths if Path(p).name.casefold() in {".env.example", ".env.sample", ".env.template"})[:20]
    domains: dict[str, list[str]] = {"startup": [], "deployment": [], "configuration": [], "api": [], "architecture": [], "runbook": []}
    for rel in docs:
        low = rel.casefold()
        name = Path(rel).name.casefold()
        if name.startswith("readme") or "getting-started" in low or "quickstart" in low:
            domains["startup"].append(rel)
        if any(x in low for x in ("deploy", "production", "docker", "ops/")):
            domains["deployment"].append(rel)
        if any(x in low for x in ("config", "environment", "settings")):
            domains["configuration"].append(rel)
        if any(x in low for x in ("api", "openapi", "swagger")):
            domains["api"].append(rel)
        if any(x in low for x in ("architect", "design", "adr")):
            domains["architecture"].append(rel)
        if any(x in low for x in ("runbook", "operations", "incident")):
            domains["runbook"].append(rel)
    if env_examples:
        domains["configuration"].extend(env_examples)
    return {
        "docs": docs,
        "env_examples": env_examples,
        "domains": {key: sorted(set(values))[:20] for key, values in domains.items() if values},
        "has_project_docs": bool(docs or env_examples),
    }
