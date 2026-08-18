from __future__ import annotations

# One canonical source for integration/bootstrap compatibility versions. These values describe
# externally installed artifacts and must never be duplicated across installer/status facades.
INTEGRATION_TEMPLATE_VERSION = 24
# v17 teaches ordinary-work hosts to keep a WorkItem open across user feedback iterations.
GLOBAL_BOOTSTRAP_VERSION = 17
GLOBAL_BOOTSTRAP_MARKER = f"<!-- AI-LAYER GLOBAL BOOTSTRAP v{GLOBAL_BOOTSTRAP_VERSION} -->"
