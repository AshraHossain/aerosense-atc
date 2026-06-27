"""Human-approval gate (AeroOps M1 — "real HITL gate on the 12-phase graph").

The design spec's example of a high-risk autonomous action ("mass diversion") maps
onto this codebase's Phase 10 ground_stop: it stops ALL departures to a fix/airport
— the single most disruptive thing the TFM agent can do. `route_after_tfm` (in
core/routing.py) is the gate's trigger: a novel, active ground_stop pauses the
graph at the `hitl_gate` node (via `interrupt_before=["hitl_gate"]` in
aerosense/graph.py) until a human calls `approve()` or `reject()`.

In-memory, like the rest of AeroSense's state — there is no database here. The
ApprovalGate is the audit-trail-friendly record of who approved what; an API/
dashboard surface to drive it is a clean follow-up, not built in this pass.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ApprovalRequest:
    id: str
    trace_id: str
    payload: dict
    reason: str
    status: str = "pending"  # pending | approved | rejected
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    decided_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "trace_id": self.trace_id, "payload": self.payload,
            "reason": self.reason, "status": self.status,
            "created_at": self.created_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
        }


class ApprovalGate:
    """In-memory approval ledger. Thread-safe: scenarios run in background
    threads (one per websocket-driven run), and approve/reject typically comes
    from a different thread (an API request) than the one that raised it."""

    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def request(self, trace_id: str, payload: dict, reason: str) -> ApprovalRequest:
        req = ApprovalRequest(id=str(uuid.uuid4()), trace_id=trace_id,
                              payload=payload, reason=reason)
        with self._lock:
            self._requests[req.id] = req
        return req

    def get(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._requests.get(approval_id)

    def _decide(self, approval_id: str, status: str, decided_by: str) -> ApprovalRequest:
        with self._lock:
            req = self._requests.get(approval_id)
            if req is None:
                raise KeyError(f"Unknown approval_id: {approval_id!r}")
            if req.status != "pending":
                raise ValueError(f"Approval {approval_id} already {req.status}")
            req.status = status
            req.decided_at = datetime.now(timezone.utc)
            req.decided_by = decided_by
            return req

    def approve(self, approval_id: str, decided_by: str = "human") -> ApprovalRequest:
        return self._decide(approval_id, "approved", decided_by)

    def reject(self, approval_id: str, decided_by: str = "human") -> ApprovalRequest:
        return self._decide(approval_id, "rejected", decided_by)

    def pending(self) -> list[ApprovalRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.status == "pending"]

    def pending_for(self, trace_id: str) -> list[ApprovalRequest]:
        return [r for r in self.pending() if r.trace_id == trace_id]


def hitl_gate_node(state: dict) -> dict:
    """Runs only AFTER a human approves — the graph is compiled with
    interrupt_before=["hitl_gate"], so this node never executes while paused.
    The ApprovalRequest was already written by route_after_tfm (the node before
    the interrupt point), so there's nothing left to persist here."""
    return {**state, "current_phase": "hitl_gate",
            "phases_completed": state.get("phases_completed", []) + ["hitl_gate"]}


_GATE: ApprovalGate | None = None


def get_approval_gate() -> ApprovalGate:
    global _GATE
    if _GATE is None:
        _GATE = ApprovalGate()
    return _GATE
