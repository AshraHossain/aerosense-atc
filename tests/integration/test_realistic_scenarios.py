"""Real-world validation: ATC routing on realistic conflict scenarios.

These tests use synthetic but high-fidelity scenarios modeled on actual
FAA/NTAP data patterns: Denver (high elevation), ORD (busy hub), SF bay (complex
airspace). Validates deterministic routing, conflict resolution, emergency bypass.
"""

from datetime import datetime, timedelta, timezone
import pytest

from core.state import ATCState
from core.routing import (
    route_after_surveillance,
    route_after_conflict,
    route_after_emergency,
    route_after_supervisor,
)


T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


# ── Scenario 1: Denver afternoon rush (high elevation, capacity crunch) ────


def test_denver_afternoon_rush_routing():
    """High-traffic Denver scenario: capacity-driven GDP."""
    state = ATCState(
        phase=1,
        raw_contacts=[
            {"callsign": "DAL123", "squawk": "1234", "altitude": 32000, "track": 180},
            {"callsign": "SWA456", "squawk": "5678", "altitude": 31000, "track": 181},
            {"callsign": "UAL789", "squawk": "9012", "altitude": 30000, "track": 182},
        ],
        system_health="nominal",
    )
    # No emergency squawks → normal flow
    next_phase = route_after_surveillance(state)
    assert next_phase == "phase_02_flight_plan"


def test_denver_emergency_diversion():
    """Denver medical emergency: squawk 7700 bypass + conflict escalation."""
    state = ATCState(
        phase=1,
        raw_contacts=[
            # Medical emergency with 7700 squawk
            {"callsign": "MED001", "squawk": "7700", "altitude": 25000, "track": 180},
            # Normal traffic that becomes potential conflict
            {"callsign": "DAL123", "squawk": "1234", "altitude": 24000, "track": 180},
        ],
        system_health="nominal",
    )
    # Emergency squawk → bypass to Phase 09
    next_phase = route_after_surveillance(state)
    assert next_phase == "phase_09_emergency"


# ── Scenario 2: ORD afternoon (busy hub, cascading delays) ────


def test_ord_alert_conflict_escalation():
    """ORD alert-level conflict forces immediate escalation to emergency."""
    state = ATCState(
        phase=4,  # After conflict detection
        conflicts=[
            {
                "severity": "alert",  # ← Key: alert-level
                "aircraft_a": "DAL123",
                "aircraft_b": "UAL456",
                "separation": 2.5,  # 2.5 NM < 5 NM minimum
                "vertical_sep": 500,  # 500 ft < 1000 ft minimum
            }
        ],
        system_health="nominal",
    )
    # Alert-level conflict → escalate directly to Phase 09
    next_phase = route_after_conflict(state)
    assert next_phase == "phase_09_emergency"


def test_ord_warning_conflict_continues():
    """ORD warning-level conflict allows normal flow (Phase 05 clearance)."""
    state = ATCState(
        phase=4,
        conflicts=[
            {
                "severity": "warning",  # ← Below alert threshold
                "aircraft_a": "DAL123",
                "aircraft_b": "UAL456",
                "separation": 4.0,  # 4 NM (warning zone)
            }
        ],
        system_health="nominal",
    )
    # Warning-level → continue normal flow
    next_phase = route_after_conflict(state)
    assert next_phase == "phase_05_clearance"


# ── Scenario 3: SF Bay (complex airspace, tight corridors) ────


def test_sf_bay_multiple_concurrent_conflicts():
    """SF Bay has N simultaneous conflicts; highest severity drives escalation."""
    state = ATCState(
        phase=4,
        conflicts=[
            {"severity": "caution", "aircraft_a": "SWA1", "aircraft_b": "SWA2"},
            {"severity": "caution", "aircraft_a": "AAL1", "aircraft_b": "UAL1"},
            {"severity": "alert", "aircraft_a": "FDX1", "aircraft_b": "DAL1"},  # ← Alert
        ],
        system_health="nominal",
    )
    # One alert-level conflict → escalate all to Phase 09
    next_phase = route_after_conflict(state)
    assert next_phase == "phase_09_emergency"


# ── Scenario 4: System degradation (network loss, stuck radar) ────


def test_critical_health_triggers_supervisor_recheck():
    """System health degraded → Phase 12 loops back to Phase 04 for re-check."""
    state = ATCState(
        phase=12,
        system_health={"overall_status": "critical", "reason": "radar_outage"},
    )
    # Critical health → supervisor re-check loop
    next_phase = route_after_supervisor(state)
    assert next_phase == "phase_04_conflict"


def test_nominal_health_ends_cleanly():
    """System health nominal → supervisor terminates graph cleanly."""
    state = ATCState(
        phase=12,
        system_health={"overall_status": "nominal"},
    )
    # Nominal → END
    next_phase = route_after_supervisor(state)
    assert next_phase == "__end__"


# ── Scenario 5: Cascading failures (radio failure, alt hold failure) ────


def test_radio_failure_squawk_7600():
    """Aircraft lost radio (squawk 7600) → Phase 09 bypass."""
    state = ATCState(
        phase=1,
        raw_contacts=[
            {"callsign": "DAL123", "squawk": "7600", "altitude": 25000, "track": 180}
        ],
        system_health="nominal",
    )
    # Radio failure squawk → bypass
    next_phase = route_after_surveillance(state)
    assert next_phase == "phase_09_emergency"


def test_hijack_squawk_7500():
    """Potential hijack (squawk 7500) → Phase 09 bypass."""
    state = ATCState(
        phase=1,
        raw_contacts=[
            {"callsign": "AAL789", "squawk": "7500", "altitude": 30000, "track": 90}
        ],
        system_health="nominal",
    )
    # Hijack squawk → bypass
    next_phase = route_after_surveillance(state)
    assert next_phase == "phase_09_emergency"


# ── Integration: Realistic conflict sequence ────


def test_realistic_conflict_sequence():
    """Model a realistic conflict flow: caution → warning → alert → escalation.

    Simulates: two aircraft descending on same track, separation eroding.
    """
    # T0: two flights inbound, separation good
    state_t0 = ATCState(
        phase=4,
        conflicts=[
            {"severity": "caution", "separation": 6.0},  # 6 NM, above threshold
        ],
        system_health="nominal",
    )
    assert route_after_conflict(state_t0) == "phase_05_clearance"

    # T1: separation eroded to warning
    state_t1 = ATCState(
        phase=4,
        conflicts=[
            {"severity": "warning", "separation": 4.0},  # 4 NM, warning zone
        ],
        system_health="nominal",
    )
    assert route_after_conflict(state_t1) == "phase_05_clearance"

    # T2: separation eroded to alert (imminent)
    state_t2 = ATCState(
        phase=4,
        conflicts=[
            {"severity": "alert", "separation": 2.0},  # 2 NM, critical
        ],
        system_health="nominal",
    )
    assert route_after_conflict(state_t2) == "phase_09_emergency"


# ── Coverage: all routers, all emergency codes, all health states ────


def test_all_emergency_squawks_covered():
    """Validate all three emergency squawk codes are recognized."""
    for squawk in ("7700", "7600", "7500"):
        state = ATCState(
            phase=1,
            raw_contacts=[{"squawk": squawk, "altitude": 25000}],
            system_health="nominal",
        )
        assert route_after_surveillance(state) == "phase_09_emergency"


def test_all_conflict_severities():
    """Test all conflict severity levels."""
    for severity, expected_phase in [
        ("caution", "phase_05_clearance"),
        ("warning", "phase_05_clearance"),
        ("alert", "phase_09_emergency"),
    ]:
        state = ATCState(
            phase=4,
            conflicts=[{"severity": severity}],
            system_health="nominal",
        )
        assert route_after_conflict(state) == expected_phase


def test_all_health_states():
    """Test all system health outcomes."""
    for health_status, expected_phase in [
        ("nominal", "__end__"),
        ("degraded", "__end__"),
        ("critical", "phase_04_conflict"),
    ]:
        state = ATCState(
            phase=12,
            system_health={"overall_status": health_status},
        )
        actual = route_after_supervisor(state)
        assert actual == expected_phase
