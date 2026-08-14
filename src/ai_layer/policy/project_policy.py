from __future__ import annotations

import hashlib
from pathlib import Path

from ai_layer.policy.service import dynamic_policy_parts, render_dynamic_policy_parts

PROJECT_POLICY_CONTRACT_VERSION = 1
PROJECT_POLICY_MAX_CHARS = 12_000
_KIND_PRIORITY = {
    "privacy": 3,
    "readonly": 3,
    "project": 2,
    "global": 1,
}


def _bound_policy_text(parts: list[tuple[str, str]], max_chars: int) -> str:
    """Keep project/privacy/read-only text; shorten custom global first."""
    kept = [(kind, text.strip()) for kind, text in parts if text.strip()]
    rendered = render_dynamic_policy_parts(kept)
    if len(rendered) <= max_chars:
        return rendered

    kinds = [kind for kind, _ in kept]
    bodies = [text for _, text in kept]

    def render() -> str:
        return "\n\n".join(text for text in bodies if text)

    while len(render()) > max_chars:
        remaining = [index for index, text in enumerate(bodies) if text]
        if not remaining:
            return ""
        victim = min(remaining, key=lambda index: _KIND_PRIORITY.get(kinds[index], 0))
        others = "\n\n".join(text for index, text in enumerate(bodies) if index != victim and text)
        if len(others) >= max_chars:
            bodies[victim] = ""
            continue
        budget = max_chars - len(others) - (2 if others else 0)
        bodies[victim] = bodies[victim][:budget] if budget > 0 else ""
        if budget > 0:
            break
    return render()[:max_chars]


def project_policy_snapshot(project_root: str | Path) -> dict:
    """Bounded effective project-policy payload suitable for project_status."""
    parts = dynamic_policy_parts(project_root)
    text = render_dynamic_policy_parts(parts).strip()
    encoded = text.encode("utf-8")
    rendered = _bound_policy_text(parts, PROJECT_POLICY_MAX_CHARS)
    return {
        "version": PROJECT_POLICY_CONTRACT_VERSION,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "text": rendered,
        "chars": len(text),
        "truncated": len(text) > PROJECT_POLICY_MAX_CHARS,
        "authority": (
            "Apply this effective project policy before implementation. Higher-priority user/host policy "
            "still takes precedence; current repository source remains code truth."
        ),
    }
