"""ApprovalGate unit tests — pure in-memory state machine, no graph involved.
Each test uses its own fresh ApprovalGate() instance for isolation."""

import pytest

from core.hitl.gate import ApprovalGate, ApprovalRequest, get_approval_gate


def test_request_returns_pending_approval():
    gate = ApprovalGate()
    req = gate.request("trace-1", {"program": "GS-1"}, "ground stop proposed")
    assert isinstance(req, ApprovalRequest)
    assert req.status == "pending"
    assert req.trace_id == "trace-1"


def test_request_assigns_unique_ids():
    gate = ApprovalGate()
    a = gate.request("t1", {}, "r1")
    b = gate.request("t1", {}, "r2")
    assert a.id != b.id


def test_get_returns_the_request():
    gate = ApprovalGate()
    req = gate.request("t1", {"x": 1}, "reason")
    assert gate.get(req.id) is req


def test_get_unknown_id_returns_none():
    gate = ApprovalGate()
    assert gate.get("nonexistent") is None


def test_approve_changes_status():
    gate = ApprovalGate()
    req = gate.request("t1", {}, "r")
    approved = gate.approve(req.id, decided_by="ctrl-east")
    assert approved.status == "approved"
    assert approved.decided_by == "ctrl-east"
    assert approved.decided_at is not None


def test_reject_changes_status():
    gate = ApprovalGate()
    req = gate.request("t1", {}, "r")
    rejected = gate.reject(req.id, decided_by="ctrl-west")
    assert rejected.status == "rejected"
    assert rejected.decided_by == "ctrl-west"


def test_approve_unknown_id_raises():
    gate = ApprovalGate()
    with pytest.raises(KeyError):
        gate.approve("nonexistent")


def test_approve_already_decided_raises():
    gate = ApprovalGate()
    req = gate.request("t1", {}, "r")
    gate.approve(req.id)
    with pytest.raises(ValueError, match="already approved"):
        gate.approve(req.id)


def test_reject_already_approved_raises():
    gate = ApprovalGate()
    req = gate.request("t1", {}, "r")
    gate.approve(req.id)
    with pytest.raises(ValueError, match="already approved"):
        gate.reject(req.id)


def test_pending_lists_only_undecided():
    gate = ApprovalGate()
    a = gate.request("t1", {}, "r1")
    b = gate.request("t1", {}, "r2")
    gate.approve(a.id)
    pending = gate.pending()
    assert len(pending) == 1
    assert pending[0].id == b.id


def test_pending_empty_when_all_decided():
    gate = ApprovalGate()
    req = gate.request("t1", {}, "r")
    gate.reject(req.id)
    assert gate.pending() == []


def test_pending_for_filters_by_trace_id():
    gate = ApprovalGate()
    gate.request("t1", {}, "r1")
    gate.request("t2", {}, "r2")
    assert len(gate.pending_for("t1")) == 1
    assert len(gate.pending_for("t2")) == 1
    assert len(gate.pending_for("t3")) == 0


def test_to_dict_keys():
    gate = ApprovalGate()
    req = gate.request("t1", {"a": 1}, "r")
    d = req.to_dict()
    assert set(d) == {"id", "trace_id", "payload", "reason", "status",
                      "created_at", "decided_at", "decided_by"}
    assert d["decided_at"] is None


def test_default_payload_round_trips():
    gate = ApprovalGate()
    payload = {"tfm_programs": [{"tfm_type": "ground_stop"}]}
    req = gate.request("t1", payload, "r")
    assert req.payload == payload


def test_get_approval_gate_is_a_singleton():
    assert get_approval_gate() is get_approval_gate()


def test_independent_gates_do_not_share_state():
    a, b = ApprovalGate(), ApprovalGate()
    a.request("t1", {}, "r")
    assert len(a.pending()) == 1
    assert len(b.pending()) == 0
