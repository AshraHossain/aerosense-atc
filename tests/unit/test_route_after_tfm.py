"""route_after_tfm + requires_tfm_approval tests — the predicate that decides
whether a proposed ground_stop pauses the graph for human approval.

route_after_tfm calls the GLOBAL get_approval_gate() (it has no DI parameter,
matching the other routers' style), so tests use a unique scenario_id per case
and filter via pending_for(trace_id) rather than relying on a clean global gate.
"""

import pytest

from core.hitl import get_approval_gate
from core.routing import requires_tfm_approval, route_after_tfm


# --------------------------- requires_tfm_approval -------------------------- #
def test_no_programs_does_not_require_approval():
    assert requires_tfm_approval([]) is False


def test_active_ground_stop_requires_approval():
    assert requires_tfm_approval([{"tfm_type": "ground_stop", "active": True}]) is True


def test_inactive_ground_stop_does_not_require_approval():
    assert requires_tfm_approval([{"tfm_type": "ground_stop", "active": False}]) is False


def test_miles_in_trail_does_not_require_approval():
    assert requires_tfm_approval([{"tfm_type": "miles_in_trail", "active": True}]) is False


def test_gdp_does_not_require_approval():
    assert requires_tfm_approval([{"tfm_type": "gdp", "active": True}]) is False


def test_ground_stop_among_other_programs_requires_approval():
    programs = [
        {"tfm_type": "miles_in_trail", "active": True},
        {"tfm_type": "ground_stop", "active": True},
    ]
    assert requires_tfm_approval(programs) is True


def test_missing_active_key_defaults_to_no_approval():
    assert requires_tfm_approval([{"tfm_type": "ground_stop"}]) is False


def test_missing_tfm_type_key_does_not_crash():
    assert requires_tfm_approval([{"active": True}]) is False


# ------------------------------ route_after_tfm ------------------------------ #
def test_no_programs_routes_to_audit():
    state = {"scenario_id": "tfm-test-1", "tfm_programs": []}
    assert route_after_tfm(state) == "phase_11_audit"


def test_active_ground_stop_routes_to_hitl_gate():
    state = {"scenario_id": "tfm-test-2",
             "tfm_programs": [{"tfm_type": "ground_stop", "active": True,
                              "program_id": "GS-1"}]}
    assert route_after_tfm(state) == "hitl_gate"


def test_non_ground_stop_programs_route_to_audit():
    state = {"scenario_id": "tfm-test-3",
             "tfm_programs": [{"tfm_type": "miles_in_trail", "active": True}]}
    assert route_after_tfm(state) == "phase_11_audit"


def test_missing_tfm_programs_key_routes_to_audit():
    assert route_after_tfm({"scenario_id": "tfm-test-4"}) == "phase_11_audit"


def test_escalation_writes_an_approval_request():
    state = {"scenario_id": "tfm-test-5",
             "tfm_programs": [{"tfm_type": "ground_stop", "active": True,
                              "program_id": "GS-2", "affected_fix": "COATE"}]}
    route_after_tfm(state)
    pending = get_approval_gate().pending_for("tfm-test-5")
    assert len(pending) == 1
    assert pending[0].payload["tfm_programs"][0]["program_id"] == "GS-2"


def test_non_escalation_writes_no_approval_request():
    state = {"scenario_id": "tfm-test-6", "tfm_programs": []}
    route_after_tfm(state)
    assert get_approval_gate().pending_for("tfm-test-6") == []


def test_multiple_ground_stops_recorded_in_one_request():
    state = {"scenario_id": "tfm-test-7",
             "tfm_programs": [
                 {"tfm_type": "ground_stop", "active": True, "program_id": "GS-3"},
                 {"tfm_type": "ground_stop", "active": True, "program_id": "GS-4"},
                 {"tfm_type": "miles_in_trail", "active": True, "program_id": "MIT-1"},
             ]}
    route_after_tfm(state)
    pending = get_approval_gate().pending_for("tfm-test-7")
    assert len(pending) == 1
    program_ids = {p["program_id"] for p in pending[0].payload["tfm_programs"]}
    assert program_ids == {"GS-3", "GS-4"}  # MIT excluded, only ground stops


def test_router_does_not_mutate_state():
    state = {"scenario_id": "tfm-test-8",
             "tfm_programs": [{"tfm_type": "ground_stop", "active": True}]}
    snapshot = repr(state)
    route_after_tfm(state)
    assert repr(state) == snapshot
