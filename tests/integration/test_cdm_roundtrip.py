"""End-to-end CDM seam round-trip — the whole point of M2+M3 proven in one path.

Drives the full collaborative loop the way the two real apps would, over one shared bus:

    ATC (AeroSense)                       AOC (AeroCommand)
    ───────────────                       ─────────────────
    Phase-10 TFMProgram (a dict in ATCState)
        │  tfm_to_cdm()
        ▼
    CDM DOWN directive ──publish──► bus ──drain(DOWN)──► respond_to_directive(fleet)
                                                              │
    bus ◄──drain(UP)── reconcile ◄──────────── publish ◄── CDM UP responses

These are integration tests, not a production orchestrator: the round-trip really
spans two apps over a bus, so no single function owns it — wiring it here is the
honest place. Everything is deterministic (no LLM, no network).
"""

from datetime import datetime, timedelta, timezone

import pytest

from cdm import InMemoryCDMTransport, tfm_to_cdm
from cdm.messages import (
    CDMDirection,
    CancellationNotice,
    FlightIntent,
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
)
from aerocommand import FleetFlight, respond_to_directive

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
T2 = T0 + timedelta(hours=2)


def _tfm(**over):
    base = {
        "program_id": "tfm-1", "tfm_type": "gdp", "affected_fix": "KDEN",
        "rate_per_hour": 1, "reason": "thunderstorms", "active": True,
    }
    base.update(over)
    return base


def _flight(fid, dest="KDEN", arr_min=0, priority=0, cancellable=True, fixes=None):
    return FleetFlight(flight_id=fid, origin="KSFO", destination=dest,
                       scheduled_arrival=T0 + timedelta(minutes=arr_min),
                       priority=priority, cancellable=cancellable,
                       route_fixes=fixes or [])


def run_roundtrip(tfm, fleet, *, bus=None, **ctx):
    """ATC emits a directive onto the bus; AOC drains it, responds, and publishes
    the responses back. Returns (down, directives_seen, ups, bus)."""
    bus = bus or InMemoryCDMTransport()
    down = tfm_to_cdm(tfm, issuer="ATCSCC", message_id="d1", **ctx)
    bus.publish(down)                                  # ATC -> bus
    directives = bus.drain(direction=CDMDirection.DOWN)  # AOC reads DOWN
    ups = []
    for d in directives:
        ups.extend(respond_to_directive(d, fleet))
    bus.publish_many(ups)                              # AOC -> bus
    return down, directives, ups, bus


# ── GDP full round-trip ────────────────────────────────────────────────────────

def _gdp_ctx():
    return dict(start=T0, end=T2)  # capacity = 1/hr * 2hr = 2


def test_gdp_down_message_is_ground_delay_program():
    down, _, _, _ = run_roundtrip(_tfm(), [], **_gdp_ctx())
    assert isinstance(down, GroundDelayProgram)
    assert down.direction == CDMDirection.DOWN


def test_gdp_aoc_sees_exactly_the_one_directive():
    _, directives, _, _ = run_roundtrip(_tfm(), [_flight("F0")], **_gdp_ctx())
    assert len(directives) == 1
    assert isinstance(directives[0], GroundDelayProgram)


def test_gdp_fleet_fits_yields_no_responses():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(2)]  # capacity 2
    _, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert ups == []


def test_gdp_overflow_produces_responses():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(3)]  # overflow 1
    _, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert len(ups) == 1


def test_gdp_responses_are_up_direction():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(4)]
    _, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert ups and all(u.direction == CDMDirection.UP for u in ups)


def test_gdp_lowest_priority_is_cancelled():
    fleet = [_flight("HI", priority=9, arr_min=0),
             _flight("LO", priority=1, arr_min=1),
             _flight("MID", priority=5, arr_min=2)]
    _, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert len(ups) == 1
    assert ups[0].flight_id == "LO"
    assert isinstance(ups[0], CancellationNotice)


def test_gdp_non_cancellable_victim_is_delayed():
    fleet = [_flight("A", priority=5, arr_min=0),
             _flight("B", priority=5, arr_min=1),
             _flight("LOCK", priority=1, arr_min=2, cancellable=False)]
    _, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert isinstance(ups[0], FlightIntent) and ups[0].intended_action == "delay"


def test_gdp_atc_can_reconcile_up_messages_from_bus():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(3)]
    _, _, ups, bus = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    reconciled = bus.drain(direction=CDMDirection.UP)
    assert [m.message_id for m in reconciled] == [u.message_id for u in ups]


def test_gdp_bus_empty_after_full_cycle():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(3)]
    _, _, _, bus = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    bus.drain(direction=CDMDirection.UP)
    assert bus.pending == 0


def test_gdp_down_not_returned_to_aoc_again():
    # after AOC drains DOWN, only UP responses remain
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(3)]
    _, _, _, bus = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert bus.drain(direction=CDMDirection.DOWN) == []


def test_gdp_missing_window_fails_before_bus():
    with pytest.raises(ValueError):
        run_roundtrip(_tfm(), [_flight("F0")])  # no start/end


def test_gdp_reason_carried_to_wire():
    down, _, _, _ = run_roundtrip(_tfm(reason="volcanic ash"), [], **_gdp_ctx())
    assert down.reason == "volcanic ash"


def test_gdp_element_carried_to_wire():
    down, _, _, _ = run_roundtrip(_tfm(affected_fix="KJFK"), [], **_gdp_ctx())
    assert down.element == "KJFK"


def test_gdp_other_destination_flights_untouched():
    fleet = [_flight("DEN1", dest="KDEN", arr_min=0),
             _flight("DEN2", dest="KDEN", arr_min=1),
             _flight("DEN3", dest="KDEN", arr_min=2),
             _flight("ORD1", dest="KORD", arr_min=0)]
    _, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    assert all(u.flight_id.startswith("DEN") for u in ups)


def test_gdp_roundtrip_is_deterministic():
    fleet = [_flight(f"F{i}", arr_min=i, priority=i % 3) for i in range(8)]
    a = run_roundtrip(_tfm(), fleet, **_gdp_ctx())[2]
    b = run_roundtrip(_tfm(), fleet, **_gdp_ctx())[2]
    assert [(m.flight_id, type(m).__name__) for m in a] == \
           [(m.flight_id, type(m).__name__) for m in b]


# ── Ground-stop full round-trip ────────────────────────────────────────────────

def test_ground_stop_down_type():
    down, _, _, _ = run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                                  [], until=T2)
    assert isinstance(down, GroundStop)


def test_ground_stop_delays_all_affected():
    fleet = [_flight("A", dest="KORD", arr_min=0),
             _flight("B", dest="KORD", arr_min=1)]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                                 fleet, until=T2)
    assert {u.flight_id for u in ups} == {"A", "B"}
    assert all(u.intended_action == "delay" for u in ups)


def test_ground_stop_unaffected_destination():
    fleet = [_flight("A", dest="KDEN", arr_min=0)]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                                 fleet, until=T2)
    assert ups == []


def test_ground_stop_requires_until():
    with pytest.raises(ValueError):
        run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"), [])


def test_ground_stop_ups_are_up_direction():
    fleet = [_flight("A", dest="KORD")]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                                 fleet, until=T2)
    assert all(u.direction == CDMDirection.UP for u in ups)


def test_ground_stop_atc_reconciles():
    fleet = [_flight(f"F{i}", dest="KORD", arr_min=i) for i in range(3)]
    _, _, ups, bus = run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                                   fleet, until=T2)
    assert len(bus.drain(direction=CDMDirection.UP)) == len(ups) == 3


def test_ground_stop_ordered_by_arrival():
    fleet = [_flight("LATE", dest="KORD", arr_min=50),
             _flight("EARLY", dest="KORD", arr_min=5)]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                                 fleet, until=T2)
    assert [u.flight_id for u in ups] == ["EARLY", "LATE"]


# ── Miles-in-trail full round-trip ─────────────────────────────────────────────

def test_mit_down_type():
    down, _, _, _ = run_roundtrip(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                                  [], miles=20, altitude_ft=33000)
    assert isinstance(down, MilesInTrail)


def test_mit_delays_flights_over_fix():
    fleet = [_flight("OVER", fixes=["BOZEE"]), _flight("CLEAR", fixes=["XYZ"])]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                                 fleet, miles=20, altitude_ft=33000)
    assert {u.flight_id for u in ups} == {"OVER"}


def test_mit_no_flights_over_fix():
    fleet = [_flight("A", fixes=["XYZ"])]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                                 fleet, miles=20, altitude_ft=33000)
    assert ups == []


def test_mit_requires_miles_and_altitude():
    with pytest.raises(ValueError):
        run_roundtrip(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"), [], miles=20)


def test_mit_all_delay_intents():
    fleet = [_flight(f"F{i}", arr_min=i, fixes=["BOZEE"]) for i in range(3)]
    _, _, ups, _ = run_roundtrip(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                                 fleet, miles=15, altitude_ft=30000)
    assert all(isinstance(u, FlightIntent) and u.intended_action == "delay" for u in ups)


def test_mit_atc_reconciles():
    fleet = [_flight(f"F{i}", arr_min=i, fixes=["BOZEE"]) for i in range(4)]
    _, _, ups, bus = run_roundtrip(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                                   fleet, miles=15, altitude_ft=30000)
    assert len(bus.drain(direction=CDMDirection.UP)) == len(ups) == 4


# ── Bus / multi-directive integration ──────────────────────────────────────────

def test_unknown_tfm_type_fails_before_publish():
    bus = InMemoryCDMTransport()
    with pytest.raises(ValueError):
        run_roundtrip(_tfm(tfm_type="warp_drive"), [], bus=bus)
    assert bus.pending == 0  # nothing leaked onto the bus


def test_two_directives_on_one_bus_drain_independently():
    bus = InMemoryCDMTransport()
    g = tfm_to_cdm(_tfm(), issuer="ATCSCC", message_id="g1", start=T0, end=T2)
    s = tfm_to_cdm(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                   issuer="ATCSCC", message_id="s1", until=T2)
    bus.publish_many([g, s])
    downs = bus.drain(direction=CDMDirection.DOWN)
    assert [type(d).__name__ for d in downs] == ["GroundDelayProgram", "GroundStop"]


def test_up_and_down_coexist_on_bus_and_filter_cleanly():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(3)]
    down, _, ups, bus = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    # publish a fresh DOWN after the cycle; UP responses still queued
    bus.publish(down)
    assert bus.pending == len(ups) + 1
    assert len(bus.drain(direction=CDMDirection.UP)) == len(ups)
    assert len(bus.drain(direction=CDMDirection.DOWN)) == 1


def test_wire_serialization_survives_roundtrip():
    fleet = [_flight(f"F{i}", arr_min=i) for i in range(3)]
    down, _, ups, _ = run_roundtrip(_tfm(), fleet, **_gdp_ctx())
    # the DOWN directive survives a JSON hop (as it would over Kafka in M4)
    restored = GroundDelayProgram.model_validate_json(down.model_dump_json())
    assert restored.element == down.element
    # so does an UP response
    up0 = CancellationNotice.model_validate_json(ups[0].model_dump_json())
    assert up0.flight_id == ups[0].flight_id


def test_empty_fleet_full_cycle_is_clean():
    _, directives, ups, bus = run_roundtrip(_tfm(), [], **_gdp_ctx())
    assert len(directives) == 1 and ups == [] and bus.pending == 0


@pytest.mark.parametrize("n_flights,capacity,expected_ups", [
    (0, 2, 0), (1, 2, 0), (2, 2, 0), (3, 2, 1), (5, 2, 3), (10, 2, 8),
])
def test_gdp_overflow_counts_parametrized(n_flights, capacity, expected_ups):
    fleet = [_flight(f"F{i:02d}", arr_min=i, priority=i) for i in range(n_flights)]
    _, _, ups, _ = run_roundtrip(_tfm(rate=1), fleet, start=T0, end=T2)
    assert len(ups) == expected_ups


def test_issuer_on_down_is_atc():
    down, _, _, _ = run_roundtrip(_tfm(), [], **_gdp_ctx())
    assert down.issuer == "ATCSCC"
