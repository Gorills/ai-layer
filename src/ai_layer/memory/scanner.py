"""Compatibility facade for deterministic repository evidence scanning.

Physical source discovery/parsing lives in ``memory.source``; incremental identity and
evidence orchestration live in their own lower-level modules. Existing imports from
``memory.scanner`` remain valid without introducing reverse dependencies.
"""

from __future__ import annotations

from ai_layer.memory.identity import build_file_hints as build_file_state
from ai_layer.memory.indexer import scan_project
from ai_layer.memory.persistence import upsert_project_file as _upsert_project_file
from ai_layer.memory.source import (
    AI_LAYER_CONTROL_PATHS,
    BINARY_EXTS,
    IGNORE_DIRS,
    IMPORTANT_NAMES,
    LANG_BY_EXT,
    SAFE_ENV_TEMPLATE_NAMES,
    SENSITIVE_NAMES,
    SENSITIVE_SUFFIXES,
    SHARED_AGENT_INSTRUCTION_PATHS,
    ScanLimitExceeded,
    architecture_summary,
    extract_imports,
    infer_purpose,
    iter_files,
    language_for,
    parse_dependencies,
    prepare_index_text,
    read_stable_source,
    read_stable_text,
    read_text,
    redact_secrets,
    risk_flags,
)

__all__ = [
    "AI_LAYER_CONTROL_PATHS",
    "BINARY_EXTS",
    "IGNORE_DIRS",
    "IMPORTANT_NAMES",
    "LANG_BY_EXT",
    "SAFE_ENV_TEMPLATE_NAMES",
    "ScanLimitExceeded",
    "SENSITIVE_NAMES",
    "SENSITIVE_SUFFIXES",
    "SHARED_AGENT_INSTRUCTION_PATHS",
    "_upsert_project_file",
    "architecture_summary",
    "build_file_state",
    "extract_imports",
    "infer_purpose",
    "iter_files",
    "language_for",
    "parse_dependencies",
    "prepare_index_text",
    "read_stable_source",
    "read_stable_text",
    "read_text",
    "redact_secrets",
    "risk_flags",
    "scan_project",
]
