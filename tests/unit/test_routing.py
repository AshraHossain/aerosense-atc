"""Deterministic router tests — the safety-critical core. These encode the
emergency-bypass and conflict-escalation rules that must never regress. No LLM,
no API key, no agents imported: routing is pure Python and stays that way."""

from langgraph.graph import END

from core.routing import (
    EMERGENCY_SQUAWKS,
    route_after_conflict,
    route_after_emergency,
    route_after_supervisor,
    route_after_surveillance,
)


# ----------------------- route_after_surveillance -------------------------- #
def test_no_contacts_routes_to_flight_plan():
    assert route_after_surveillance({"raw_contacts": []}) == "phase_02_flight_plan"


def test_missing_raw_contacts_key_defaults_to_flight_plan():
    assert route_after_surveillance({}) == "phase_02_flight_plan"


def test_normal_squawk_routes_to_flight_plan():
    state = {"raw_contacts": [{"squawk": "1200"}, {"squawk": "4567"}]}
    assert route_after_surveillance(state) == "phase_02_flight_plan"


def test_mayday_7700_bypasses_to_emergency():
    state = {"raw_contacts": [{"squawk": "7700"}]}
    assert route_after_surveillance(state) == "phase_09_emergency"


def test_radiofail_7600_bypasses_to_emergency():
    state = {"raw_contacts": [{"squawk": "7600"}]}
    assert route_after_surveillance(state) == "phase_09_emergency"


def test_hijack_7500_bypasses_to_emergency():
    state = {"raw_contacts": [{"squawk": "7500"}]}
    assert route_after_surveillance(state) == "phase_09_emergency"


def test_emergency_squawk_among_normal_contacts_still_bypasses():
    state = {"raw_contacts": [{"squawk": "1200"}, {"squawk": "7700"}, {"squawk": "4567"}]}
    assert route_after_surveillance(state) == "phase_09_emergency"


def test_contact_without_squawk_key_is_ignored():
    state = {"raw_contacts": [{"callsign": "UAL123"}]}
    assert route_after_surveillance(state) == "phase_02_flight_plan"


def test_all_three_emergency_squawks_are_recognized():
    for code in EMERGENCY_SQUAWKS:
        assert route_after_surveillance({"raw_contacts": [{"squawk": code}]}) \
            == "phase_09_emergency"


def test_emergency_squawks_constant_is_exactly_the_three_codes():
    assert set(EMERGENCY_SQUAWKS) == {"7700", "7600", "7500"}


def test_squawk_as_int_does_not_match_string_codes():
    # raw contacts carry squawk as a string; an int 7700 must not match (documents
    # the contract that surveillance normalizes squawk to str upstream).
    state = {"raw_contacts": [{"squawk": 7700}]}
    assert route_after_surveillance(state) == "phase_02_flight_plan"


# ------------------------- route_after_conflict ---------------------------- #
def test_no_conflicts_routes_to_clearance():
    assert route_after_conflict({"conflicts": []}) == "phase_05_clearance"


def test_missing_conflicts_key_defaults_to_clearance():
    assert route_after_conflict({}) == "phase_05_clearance"


def test_advisory_conflict_routes_to_clearance():
    state = {"conflicts": [{"severity": "advisory"}]}
    assert route_after_conflict(state) == "phase_05_clearance"


def test_warning_conflict_routes_to_clearance():
    state = {"conflicts": [{"severity": "warning"}]}
    assert route_after_conflict(state) == "phase_05_clearance"


def test_alert_conflict_bypasses_to_emergency():
    state = {"conflicts": [{"severity": "alert"}]}
    assert route_after_conflict(state) == "phase_09_emergency"


def test_alert_among_lower_severities_still_bypasses():
    state = {"conflicts": [{"severity": "advisory"}, {"severity": "alert"},
                           {"severity": "warning"}]}
    assert route_after_conflict(state) == "phase_09_emergency"


def test_conflict_without_severity_key_ignored():
    state = {"conflicts": [{"conflict_id": "C1"}]}
    assert route_after_conflict(state) == "phase_05_clearance"


# ------------------------ route_after_emergency ---------------------------- #
def test_emergency_always_resumes_at_clearance():
    assert route_after_emergency({}) == "phase_05_clearance"
    assert route_after_emergency({"emergencies": [{"status": "active"}]}) \
        == "phase_05_clearance"


# ------------------------ route_after_supervisor --------------------------- #
def test_critical_health_loops_back_to_conflict():
    state = {"system_health": {"overall_status": "critical"}}
    assert route_after_supervisor(state) == "phase_04_conflict"


def test_nominal_health_terminates():
    state = {"system_health": {"overall_status": "nominal"}}
    assert route_after_supervisor(state) == END


def test_degraded_health_terminates():
    state = {"system_health": {"overall_status": "degraded"}}
    assert route_after_supervisor(state) == END


def test_missing_health_terminates():
    assert route_after_supervisor({}) == END


def test_empty_health_dict_terminates():
    assert route_after_supervisor({"system_health": {}}) == END


# --------------------------- cross-cutting --------------------------------- #
def test_routers_are_pure_no_state_mutation():
    state = {"raw_contacts": [{"squawk": "7700"}], "conflicts": [{"severity": "alert"}],
             "system_health": {"overall_status": "critical"}}
    snapshot = repr(state)
    route_after_surveillance(state)
    route_after_conflict(state)
    route_after_emergency(state)
    route_after_supervisor(state)
    assert repr(state) == snapshot  # routers must not mutate the shared state


def test_routing_module_does_not_import_agents():
    import sys
    import core.routing  # noqa: F401
    # Importing routing must not have pulled in the agent package or genai.
    assert "agents" not in sys.modules or not any(
        m.startswith("agents.phase_") for m in sys.modules
    )
