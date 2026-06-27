"""AOC responder tests — deterministic GDP/ground-stop/MIT reactions. No LLM, no network."""

from datetime import datetime, timedelta, timezone

import pytest

from cdm.messages import (
    CancellationNotice,
    FlightIntent,
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
    SubstitutionRequest,
    SlotSwap,
)
from aerocommand.fleet import FleetFlight
from aerocommand.responder import (
    respond_to_directive,
    respond_to_gdp,
    respond_to_ground_stop,
    respond_to_miles_in_trail,
)

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
T2 = T0 + timedelta(hours=2)


def gdp(element="KDEN", rate=2, start=T0, end=T2):
    return GroundDelayProgram(message_id="g", issuer="ATCSCC", element=element,
                              program_rate_per_hour=rate, start=start, end=end,
                              reason="wx")


def flight(fid, dest="KDEN", arr_min=0, priority=0, cancellable=True, fixes=None):
    return FleetFlight(flight_id=fid, origin="KSFO", destination=dest,
                       scheduled_arrival=T0 + timedelta(minutes=arr_min),
                       priority=priority, cancellable=cancellable,
                       route_fixes=fixes or [])


# ── GDP: capacity / overflow ───────────────────────────────────────────────────

def test_gdp_everyone_fits_no_action():
    # rate 2/hr * 2hr = capacity 4; only 3 arrivals
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    assert respond_to_gdp(gdp(rate=2), flights) == []


def test_gdp_exact_capacity_no_action():
    flights = [flight(f"F{i}", arr_min=i) for i in range(4)]  # capacity 4
    assert respond_to_gdp(gdp(rate=2), flights) == []


def test_gdp_one_over_capacity_one_victim():
    flights = [flight(f"F{i}", arr_min=i) for i in range(5)]  # capacity 4, overflow 1
    out = respond_to_gdp(gdp(rate=2), flights)
    assert len(out) == 1


def test_gdp_victim_is_lowest_priority():
    flights = [
        flight("HIGH", arr_min=0, priority=10),
        flight("LOW", arr_min=1, priority=1),
        flight("MID", arr_min=2, priority=5),
    ]
    # capacity 2 (rate 1/hr * 2hr), overflow 1 -> lowest priority "LOW" is the victim
    out = respond_to_gdp(gdp(rate=1), flights)
    assert len(out) == 1
    assert out[0].flight_id == "LOW"


def test_gdp_victim_cancelled_when_cancellable():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]  # cap 2, overflow 1
    out = respond_to_gdp(gdp(rate=1), flights)
    assert isinstance(out[0], CancellationNotice)


def test_gdp_victim_delayed_when_not_cancellable():
    flights = [
        flight("A", arr_min=0, priority=5),
        flight("B", arr_min=1, priority=5),
        flight("LOCK", arr_min=2, priority=1, cancellable=False),
    ]
    out = respond_to_gdp(gdp(rate=1), flights)  # cap 2, overflow 1, victim LOCK
    assert len(out) == 1
    assert isinstance(out[0], FlightIntent)
    assert out[0].intended_action == "delay"
    assert out[0].flight_id == "LOCK"


def test_gdp_mixed_cancel_and_delay():
    flights = [
        flight("KEEP", arr_min=0, priority=10),
        flight("CXL", arr_min=1, priority=1, cancellable=True),
        flight("LOCK", arr_min=2, priority=2, cancellable=False),
    ]
    # cap 1 (rate ~0.5/hr*2hr=1), overflow 2 -> victims = two lowest priority: CXL, LOCK
    out = respond_to_gdp(
        GroundDelayProgram(message_id="g", issuer="ATCSCC", element="KDEN",
                           program_rate_per_hour=1, start=T0, end=T0 + timedelta(hours=1),
                           reason="wx"),
        flights,
    )
    kinds = {m.flight_id: type(m).__name__ for m in out}
    assert kinds == {"CXL": "CancellationNotice", "LOCK": "FlightIntent"}


def test_gdp_high_priority_protected():
    flights = [flight(f"F{i}", arr_min=i, priority=1) for i in range(4)]
    flights.append(flight("VIP", arr_min=5, priority=100))
    out = respond_to_gdp(gdp(rate=2), flights)  # cap 4, overflow 1
    victim_ids = {m.flight_id for m in out}
    assert "VIP" not in victim_ids


def test_gdp_only_destination_matched():
    flights = [flight("TO_DEN", dest="KDEN", arr_min=0),
               flight("TO_ORD", dest="KORD", arr_min=1)]
    # capacity 0 forces overflow only among KDEN arrivals
    out = respond_to_gdp(gdp(element="KDEN", rate=1, start=T0,
                             end=T0 + timedelta(minutes=1)), flights)
    assert {m.flight_id for m in out} == {"TO_DEN"}


def test_gdp_tie_break_by_flight_id():
    # two equal-priority victims candidates; lower flight_id chosen first deterministically
    flights = [flight("B", arr_min=0, priority=1),
               flight("A", arr_min=1, priority=1),
               flight("C", arr_min=2, priority=9)]
    out = respond_to_gdp(gdp(rate=1), flights)  # cap 2 overflow 1
    assert out[0].flight_id == "A"  # lowest id among the priority-1 pair


def test_gdp_capacity_floor():
    # rate 3/hr * 1.5hr = 4.5 -> floored to 4
    flights = [flight(f"F{i}", arr_min=i) for i in range(5)]
    out = respond_to_gdp(
        GroundDelayProgram(message_id="g", issuer="ATCSCC", element="KDEN",
                           program_rate_per_hour=3, start=T0,
                           end=T0 + timedelta(minutes=90), reason="wx"),
        flights,
    )
    assert len(out) == 1  # 5 - floor(4.5)=4 -> overflow 1


def test_gdp_empty_fleet():
    assert respond_to_gdp(gdp(), []) == []


def test_gdp_cancellation_reason_is_set():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    out = respond_to_gdp(gdp(rate=1), flights)
    assert out[0].reason  # non-empty


def test_gdp_messages_are_up_direction():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    out = respond_to_gdp(gdp(rate=1), flights)
    from cdm.messages import CDMDirection
    assert all(m.direction == CDMDirection.UP for m in out)


def test_gdp_unique_message_ids():
    flights = [flight(f"F{i}", arr_min=i, priority=i) for i in range(6)]
    out = respond_to_gdp(gdp(rate=1), flights)  # cap 2 overflow 4
    ids = [m.message_id for m in out]
    assert len(ids) == len(set(ids))


def test_gdp_issuer_propagates():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    out = respond_to_gdp(gdp(rate=1), flights, issuer="DAL-OCC")
    assert out[0].issuer == "DAL-OCC"


# ── Ground stop ────────────────────────────────────────────────────────────────

def test_ground_stop_delays_all_affected():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T2)
    flights = [flight("A", dest="KORD", arr_min=0),
               flight("B", dest="KORD", arr_min=1),
               flight("C", dest="KDEN", arr_min=2)]
    out = respond_to_ground_stop(stop, flights)
    assert {m.flight_id for m in out} == {"A", "B"}
    assert all(m.intended_action == "delay" for m in out)


def test_ground_stop_no_affected_flights():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KSEA",
                      reason="fog", until=T2)
    flights = [flight("A", dest="KORD", arr_min=0)]
    assert respond_to_ground_stop(stop, flights) == []


def test_ground_stop_sorted_by_arrival():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T2)
    flights = [flight("LATE", dest="KORD", arr_min=30),
               flight("EARLY", dest="KORD", arr_min=5)]
    out = respond_to_ground_stop(stop, flights)
    assert [m.flight_id for m in out] == ["EARLY", "LATE"]


def test_ground_stop_details_mention_until():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T2)
    out = respond_to_ground_stop(stop, [flight("A", dest="KORD")])
    assert "ground stop" in out[0].details


# ── Miles-in-trail ─────────────────────────────────────────────────────────────

def mit(fix="BOZEE", miles=20):
    return MilesInTrail(message_id="m", issuer="ATCSCC", fix=fix, miles=miles,
                        altitude_ft=33000)


def test_mit_delays_flights_over_fix():
    flights = [flight("OVER", fixes=["BOZEE", "DEN"]),
               flight("CLEAR", fixes=["OTHER"])]
    out = respond_to_miles_in_trail(mit(), flights)
    assert {m.flight_id for m in out} == {"OVER"}


def test_mit_no_flights_over_fix():
    flights = [flight("A", fixes=["XYZ"])]
    assert respond_to_miles_in_trail(mit(), flights) == []


def test_mit_all_delay_intents():
    flights = [flight(f"F{i}", arr_min=i, fixes=["BOZEE"]) for i in range(3)]
    out = respond_to_miles_in_trail(mit(), flights)
    assert all(isinstance(m, FlightIntent) and m.intended_action == "delay" for m in out)


def test_mit_details_mention_fix_and_miles():
    out = respond_to_miles_in_trail(mit(fix="BOZEE", miles=15),
                                    [flight("A", fixes=["BOZEE"])])
    assert "BOZEE" in out[0].details and "15" in out[0].details


def test_mit_sorted_by_arrival():
    flights = [flight("LATE", arr_min=40, fixes=["BOZEE"]),
               flight("EARLY", arr_min=2, fixes=["BOZEE"])]
    out = respond_to_miles_in_trail(mit(), flights)
    assert [m.flight_id for m in out] == ["EARLY", "LATE"]


# ── Dispatcher ─────────────────────────────────────────────────────────────────

def test_dispatch_routes_gdp():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    out = respond_to_directive(gdp(rate=1), flights)
    assert isinstance(out[0], (CancellationNotice, FlightIntent))


def test_dispatch_routes_ground_stop():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T2)
    out = respond_to_directive(stop, [flight("A", dest="KORD")])
    assert out[0].intended_action == "delay"


def test_dispatch_routes_mit():
    out = respond_to_directive(mit(), [flight("A", fixes=["BOZEE"])])
    assert out[0].intended_action == "delay"


def test_dispatch_rejects_up_message():
    up = SubstitutionRequest(message_id="u", issuer="DAL-OCC", program_id="g",
                             swaps=[SlotSwap(cancel_flight="X", promote_flight="Y")])
    with pytest.raises(ValueError):
        respond_to_directive(up, [])


def test_dispatch_rejects_flight_intent_as_input():
    intent = FlightIntent(message_id="u", issuer="DAL-OCC", flight_id="A",
                          intended_action="continue")
    with pytest.raises(ValueError):
        respond_to_directive(intent, [])


def test_dispatch_empty_fleet_gdp():
    assert respond_to_directive(gdp(), []) == []


# ── More edge cases (determinism, serialization, scale) ────────────────────────

def test_gdp_zero_capacity_cancels_all_cancellable():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    # rate 1/hr over 1 minute -> capacity floor(0.0166) = 0 -> overflow 3
    out = respond_to_gdp(
        GroundDelayProgram(message_id="g", issuer="ATCSCC", element="KDEN",
                           program_rate_per_hour=1, start=T0,
                           end=T0 + timedelta(minutes=1), reason="wx"),
        flights,
    )
    assert len(out) == 3
    assert all(isinstance(m, CancellationNotice) for m in out)


def test_gdp_large_overflow_handles_every_victim():
    flights = [flight(f"F{i:02d}", arr_min=i, priority=i) for i in range(20)]
    out = respond_to_gdp(gdp(rate=2), flights)  # cap 4 overflow 16
    assert len(out) == 16


def test_gdp_victims_are_the_16_lowest_priority():
    flights = [flight(f"F{i:02d}", arr_min=i, priority=i) for i in range(20)]
    out = respond_to_gdp(gdp(rate=2), flights)  # protects the 4 highest priority
    survivors = {f"F{i:02d}" for i in range(16, 20)}
    victim_ids = {m.flight_id for m in out}
    assert victim_ids.isdisjoint(survivors)


def test_gdp_output_is_deterministic_across_runs():
    flights = [flight(f"F{i}", arr_min=i, priority=(i % 3)) for i in range(8)]
    a = [(m.flight_id, type(m).__name__) for m in respond_to_gdp(gdp(rate=1), flights)]
    b = [(m.flight_id, type(m).__name__) for m in respond_to_gdp(gdp(rate=1), flights)]
    assert a == b


def test_gdp_cancellation_json_round_trips():
    flights = [flight(f"F{i}", arr_min=i) for i in range(3)]
    out = respond_to_gdp(gdp(rate=1), flights)
    restored = CancellationNotice.model_validate_json(out[0].model_dump_json())
    assert restored.flight_id == out[0].flight_id


def test_ground_stop_unique_message_ids():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T2)
    flights = [flight(f"F{i}", dest="KORD", arr_min=i) for i in range(5)]
    out = respond_to_ground_stop(stop, flights)
    assert len({m.message_id for m in out}) == 5


def test_ground_stop_issuer_propagates():
    stop = GroundStop(message_id="s", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T2)
    out = respond_to_ground_stop(stop, [flight("A", dest="KORD")], issuer="UAL-OCC")
    assert out[0].issuer == "UAL-OCC"


def test_mit_issuer_propagates():
    out = respond_to_miles_in_trail(mit(), [flight("A", fixes=["BOZEE"])],
                                    issuer="SWA-OCC")
    assert out[0].issuer == "SWA-OCC"


def test_mit_flight_on_multiple_constrained_fixes_counts_once():
    out = respond_to_miles_in_trail(mit(fix="BOZEE"),
                                    [flight("A", fixes=["BOZEE", "BOZEE"])])
    assert len(out) == 1
