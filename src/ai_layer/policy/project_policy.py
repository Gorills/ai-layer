from __future__ import annotations

import hashlib
from pathlib import Path

from ai_layer.policy.service import dynamic_policy

PROJECT_POLICY_CONTRACT_VERSION = 1
PROJECT_POLICY_MAX_CHARS = 12_000


def project_policy_snapshot(project_root: str | Path) -> dict:
    """Bounded effective project-policy payload suitable for project_status."""
    text = dynamic_policy(project_root).strip()
    encoded = text.encode("utf-8")
    rendered = text[:PROJECT_POLICY_MAX_CHARS]
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
