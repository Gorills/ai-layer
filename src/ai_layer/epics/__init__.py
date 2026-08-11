"""Epic domain contracts.

Epics own durable specification/approval/reconciliation semantics and scheduling intent.
Application services coordinate persistence and invoke the existing Task Engine; Epic code
never reimplements Task stages, leases, snapshots, verification, review/fix, or findings.
"""

from ai_layer.epics.contracts import epic_key, phase0_contract, spec_quality

__all__ = ["epic_key", "phase0_contract", "spec_quality"]
