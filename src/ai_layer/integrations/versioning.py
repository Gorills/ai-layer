from __future__ import annotations

# One canonical source for integration/bootstrap compatibility versions. These values describe
# externally installed artifacts and must never be duplicated across installer/status facades.
INTEGRATION_TEMPLATE_VERSION = 24
# v18 makes tool/schema/project-context errors fail closed until corrected and retried.
GLOBAL_BOOTSTRAP_VERSION = 18
GLOBAL_BOOTSTRAP_MARKER = f"<!-- AI-LAYER GLOBAL BOOTSTRAP v{GLOBAL_BOOTSTRAP_VERSION} -->"
