"""ATCState schema tests — ATCState is the integration contract every one of the
12 phases reads and writes, so its shape is safety-relevant. TypedDicts aren't
enforced at runtime; these tests pin the *contract* (expected keys/fields) so an
accidental rename ripples into a failing test instead of silent breakage."""

from core.state import (
    ATCState,
    Clearance,
    ConflictAlert,
    DO178CTrace,
    Emergency,
    FlightTrack,
    Position,
    TFMProgram,
)


def test_atcstate_has_all_phase_output_keys():
    keys = set(ATCState.__annotations__)
    expected = {
        "scenario_id", "scenario_name", "sim_time", "current_phase",
        "phases_completed", "raw_contacts", "flights", "flight_plans",
        "sectors", "sector_assignments", "conflicts", "clearances",
        "transmissions", "handoffs", "weather_hazards", "weather_reroutes",
        "emergencies", "tfm_programs", "do178c_traces", "system_health",
        "final_report", "events",
    }
    missing = expected - keys
    assert not missing, f"ATCState missing keys: {missing}"


def test_atcstate_can_be_constructed_minimally():
    state: ATCState = {
        "scenario_id": "s1", "scenario_name": "Nominal", "sim_time": "2026-01-01T00:00:00Z",
        "current_phase": "phase_01_surveillance", "phases_completed": [],
        "raw_contacts": [], "flights": [], "flight_plans": {}, "sectors": {},
        "sector_assignments": {}, "conflicts": [], "clearances": [],
        "transmissions": [], "handoffs": [], "weather_hazards": [],
        "weather_reroutes": [], "emergencies": [], "tfm_programs": [],
        "do178c_traces": [], "system_health": {}, "final_report": "", "events": [],
    }
    assert state["scenario_name"] == "Nominal"


def test_position_fields():
    assert set(Position.__annotations__) == {"lat", "lon", "alt_ft"}


def test_flight_track_fields():
    expected = {"callsign", "squawk", "position", "heading_deg", "speed_kts",
                "vertical_rate_fpm", "track_quality", "data_sources"}
    assert set(FlightTrack.__annotations__) == expected


def test_conflict_alert_has_separation_fields():
    fields = set(ConflictAlert.__annotations__)
    assert {"horiz_sep_nm", "vert_sep_ft", "time_to_conflict_min", "severity"} <= fields


def test_clearance_links_to_conflict():
    assert "resolves_conflict" in Clearance.__annotations__


def test_emergency_has_priority_level():
    assert "priority_level" in Emergency.__annotations__


def test_tfm_program_types_documented():
    assert "tfm_type" in TFMProgram.__annotations__


def test_do178c_trace_has_traceability_fields():
    fields = set(DO178CTrace.__annotations__)
    expected = {"trace_id", "phase_number", "phase_name", "decision", "rationale",
                "safety_constraints_verified", "determinism_flag"}
    assert expected <= fields


def test_constructable_flight_track():
    ft: FlightTrack = {
        "callsign": "UAL123", "squawk": "1200",
        "position": {"lat": 40.0, "lon": -74.0, "alt_ft": 12000},
        "heading_deg": 90, "speed_kts": 250, "vertical_rate_fpm": 0,
        "track_quality": 0.95, "data_sources": ["adsb"],
    }
    assert ft["position"]["alt_ft"] == 12000


def test_emergency_constructable():
    e: Emergency = {
        "emergency_id": "E1", "callsign": "DAL9", "emergency_type": "mayday",
        "declared_at": "2026-01-01T00:00:00Z", "priority_level": 1,
        "handling_instructions": "vector for nearest", "status": "active",
    }
    assert e["priority_level"] == 1


def test_atcstate_key_count_is_stable():
    # Tripwire: adding/removing a top-level key is a contract change that ripples
    # across all 12 phases — force a conscious update of this number.
    assert len(ATCState.__annotations__) == 22
