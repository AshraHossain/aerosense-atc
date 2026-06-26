"""Golden safety-check tests. Each check is a distinct safety assertion about the
deterministic routers; parametrizing over CHECKS makes every one its own test."""

import pytest

from core.eval.golden import (
    CHECKS,
    GOLDEN_CONFLICT,
    GOLDEN_EMERGENCY,
    GOLDEN_NOMINAL,
    GOLDEN_STATES,
    EvalCheck,
)
from core.routing import route_after_conflict, route_after_surveillance


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.name)
def test_golden_check_passes(check: EvalCheck):
    assert check.predicate() is True, check.description


def test_checks_cover_both_categories():
    cats = {c.category for c in CHECKS}
    assert cats == {"routing", "structure"}


def test_check_names_unique():
    names = [c.name for c in CHECKS]
    assert len(names) == len(set(names))


def test_enough_checks():
    assert len(CHECKS) >= 10


def test_three_golden_states_present():
    assert set(GOLDEN_STATES) == {"nominal", "emergency", "conflict"}


# Direct (non-harness) assertions on the safety-critical behaviour, so a failure
# names the exact scenario rather than a generic check.
def test_emergency_state_triggers_bypass():
    assert route_after_surveillance(GOLDEN_EMERGENCY) == "phase_09_emergency"


def test_nominal_state_normal_flow():
    assert route_after_surveillance(GOLDEN_NOMINAL) == "phase_02_flight_plan"


def test_conflict_state_alert_escalates():
    assert route_after_conflict(GOLDEN_CONFLICT) == "phase_09_emergency"


def test_every_golden_contact_has_squawk():
    for state in GOLDEN_STATES.values():
        for c in state["raw_contacts"]:
            assert "squawk" in c


def test_emergency_state_has_mayday():
    assert any(c["squawk"] == "7700" for c in GOLDEN_EMERGENCY["raw_contacts"])


def test_nominal_has_no_emergency_squawk():
    assert not any(c["squawk"] in ("7700", "7600", "7500")
                   for c in GOLDEN_NOMINAL["raw_contacts"])


def test_conflict_state_has_alert_conflict():
    assert any(c["severity"] == "alert" for c in GOLDEN_CONFLICT["conflicts"])


def test_evalcheck_is_frozen():
    c = CHECKS[0]
    with pytest.raises(Exception):
        c.name = "x"  # type: ignore[misc]
