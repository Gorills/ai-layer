"""Native Agent Skills facade.

Host relevance selection stays outside AI Layer. This module preserves a compact
Skill Layer import surface while descriptor contracts, filesystem ownership and
synchronization remain separate cohesive responsibilities.
"""

from ai_layer.skills.native_descriptor import (
    NATIVE_DESCRIPTOR_VERSION,
    NATIVE_MARKER,
    native_descriptor_name,
    render_native_descriptor,
    routing_overlap_warnings,
    validate_native_catalog,
    validate_routing_description,
)
from ai_layer.skills.native_files import (
    assert_native_targets_available,
    global_native_roots,
    native_catalog_files,
    remove_global_native_skills,
    remove_legacy_project_bridge,
    remove_project_native_skills,
)
from ai_layer.skills.native_sync import (
    sync_global_native_skills,
    sync_native_after_skill_change,
    sync_project_native_skills,
)

__all__ = [
    "NATIVE_DESCRIPTOR_VERSION",
    "NATIVE_MARKER",
    "assert_native_targets_available",
    "global_native_roots",
    "native_catalog_files",
    "native_descriptor_name",
    "remove_global_native_skills",
    "remove_legacy_project_bridge",
    "remove_project_native_skills",
    "render_native_descriptor",
    "routing_overlap_warnings",
    "sync_global_native_skills",
    "sync_native_after_skill_change",
    "sync_project_native_skills",
    "validate_native_catalog",
    "validate_routing_description",
]
