"""Cross-validation: the deterministic safety layer must behave correctly on the
REAL simulation scenarios, not just the self-contained golden fixtures. This is the
test that proves the golden fixtures in core/eval/golden.py faithfully represent
production scenarios. (Tests may import the app-level `simulation/` package; core
may not.)"""

import pytest

from core.routing import route_after_surveillance
from simulation.scenario_generator import SCENARIOS, generate_scenario


def test_three_builtin_scenarios_exist():
    assert {"nominal", "conflict", "emergency"} <= set(SCENARIOS)


def test_real_emergency_scenario_triggers_bypass():
    state = generate_scenario("emergency")
    assert route_after_surveillance(state) == "phase_09_emergency"


def test_real_nominal_scenario_normal_flow():
    state = generate_scenario("nominal")
    assert route_after_surveillance(state) == "phase_02_flight_plan"


def test_real_conflict_scenario_no_emergency_at_surveillance():
    state = generate_scenario("conflict")
    # conflict is detected at Phase 04, so surveillance routing is normal flow
    assert route_after_surveillance(state) == "phase_02_flight_plan"


def test_real_emergency_scenario_contains_mayday_squawk():
    state = generate_scenario("emergency")
    squawks = [c.get("squawk") for c in state["raw_contacts"]]
    assert "7700" in squawks


def test_real_nominal_scenario_has_no_emergency_squawk():
    state = generate_scenario("nominal")
    squawks = [c.get("squawk") for c in state["raw_contacts"]]
    assert not ({"7700", "7600", "7500"} & set(squawks))


def test_generated_scenario_has_required_atcstate_keys():
    state = generate_scenario("nominal")
    for key in ("scenario_id", "scenario_name", "raw_contacts", "system_health",
                "conflicts", "do178c_traces"):
        assert key in state


def test_unknown_scenario_falls_back_to_nominal():
    state = generate_scenario("does-not-exist")
    assert route_after_surveillance(state) == "phase_02_flight_plan"


@pytest.mark.parametrize("key", ["nominal", "conflict", "emergency"])
def test_router_never_crashes_on_real_scenarios(key):
    # Weather/non-aircraft contacts lack a squawk; the router must tolerate them.
    state = generate_scenario(key)
    result = route_after_surveillance(state)
    assert result in ("phase_02_flight_plan", "phase_09_emergency")
