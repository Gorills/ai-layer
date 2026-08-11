"""Repository Workspace capability.

Owns repository identity, snapshots/deltas and verification workspaces. Task business logic consumes
this capability instead of embedding Git/filesystem implementations.
"""
from ai_layer.workspace.repository import capture_repository_state, git_changed_paths, repository_changes

__all__ = ["capture_repository_state", "git_changed_paths", "repository_changes"]
