"""Compatibility facade for the dashboard read model.

Dashboard transport must not own Task/Skill business logic or persistence queries. New code imports
:mod:`ai_layer.projections.dashboard` directly.
"""
from ai_layer.projections.dashboard import *  # noqa: F403
