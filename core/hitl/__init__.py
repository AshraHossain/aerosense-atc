"""HITL — human-approval gate for high-risk autonomous actions (AeroOps M1).

The design's directory tree named this `core/hitl/` explicitly. Phase 10's
ground_stop (stop ALL departures to a fix/airport) is the concrete high-risk
action this gate covers; see core/hitl/gate.py.
"""

from core.hitl.gate import ApprovalGate, ApprovalRequest, get_approval_gate, hitl_gate_node

__all__ = ["ApprovalGate", "ApprovalRequest", "get_approval_gate", "hitl_gate_node"]
