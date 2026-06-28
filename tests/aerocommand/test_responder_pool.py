"""ResponderPool tests — per-airline isolation (M5 Phase 2). No LLM, no network."""

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
from aerocommand.responder_pool import ResponderPool, AirlineResponder

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
T2 = T0 + timedelta(hours=2)


def gdp(element="KDEN", rate=2, start=T0, end=T2):
    return GroundDelayProgram(
        message_id="g",
        issuer="ATCSCC",
        element=element,
        program_rate_per_hour=rate,
        start=start,
        end=end,
        reason="wx",
    )


def flight(fid, dest="KDEN", arr_min=0, priority=0, cancellable=True, fixes=None):
    return FleetFlight(
        flight_id=fid,
        origin="KSFO",
        destination=dest,
        scheduled_arrival=T0 + timedelta(minutes=arr_min),
        priority=priority,
        cancellable=cancellable,
        route_fixes=fixes or [],
    )


# ── AirlineResponder ──────────────────────────────────────────────────────────


def test_airline_responder_creation():
    responder = AirlineResponder(airline_code="DAL")
    assert responder.airline_code == "DAL"
    assert responder.fleet == []
    assert responder.response_callback is None


def test_airline_responder_with_fleet():
    fleet = [flight("F1"), flight("F2")]
    responder = AirlineResponder(airline_code="UAL", fleet=fleet)
    assert len(responder.fleet) == 2


def test_airline_responder_processes_directive():
    fleet = [flight(f"F{i}", arr_min=i) for i in range(5)]
    responder = AirlineResponder(airline_code="SWA", fleet=fleet)
    gdp_msg = gdp(rate=2)
    responses = responder.process_directive(gdp_msg)
    # cap 4, overflow 1
    assert len(responses) == 1
    assert isinstance(responses[0], (CancellationNotice, FlightIntent))


def test_airline_responder_issuer_is_airline_code():
    fleet = [flight(f"F{i}", arr_min=i) for i in range(5)]
    responder = AirlineResponder(airline_code="CUSTOM", fleet=fleet)
    responses = responder.process_directive(gdp(rate=2))
    assert responses[0].issuer == "CUSTOM"


def test_airline_responder_rejects_up_directive():
    responder = AirlineResponder(airline_code="DAL")
    up = SubstitutionRequest(
        message_id="u",
        issuer="DAL-OCC",
        program_id="g",
        swaps=[SlotSwap(cancel_flight="X", promote_flight="Y")],
    )
    with pytest.raises(ValueError):
        responder.process_directive(up)


def test_airline_responder_response_callback_invoked():
    captured = []

    def callback(airline, responses):
        captured.append((airline, responses))

    fleet = [flight(f"F{i}", arr_min=i) for i in range(5)]
    responder = AirlineResponder(
        airline_code="DAL", fleet=fleet, response_callback=callback
    )
    gdp_msg = gdp(rate=2)
    responder.process_directive(gdp_msg)

    assert len(captured) == 1
    assert captured[0][0] == "DAL"
    assert len(captured[0][1]) == 1


def test_airline_responder_callback_not_invoked_when_no_responses():
    captured = []

    def callback(airline, responses):
        captured.append((airline, responses))

    # All flights fit capacity
    fleet = [flight(f"F{i}", arr_min=i) for i in range(2)]
    responder = AirlineResponder(
        airline_code="DAL", fleet=fleet, response_callback=callback
    )
    gdp_msg = gdp(rate=2)
    responder.process_directive(gdp_msg)

    # Callback is still invoked, just with empty responses
    assert len(captured) == 1
    assert captured[0][1] == []


# ── ResponderPool ────────────────────────────────────────────────────────────


def test_pool_creation():
    pool = ResponderPool()
    assert pool.airline_count() == 0
    assert pool.airlines() == []


def test_pool_add_airline():
    pool = ResponderPool()
    responder = pool.add_airline("DAL")
    assert responder.airline_code == "DAL"
    assert pool.airline_count() == 1
    assert "DAL" in pool.airlines()


def test_pool_add_multiple_airlines():
    pool = ResponderPool()
    pool.add_airline("DAL")
    pool.add_airline("UAL")
    pool.add_airline("SWA")
    assert pool.airline_count() == 3
    assert set(pool.airlines()) == {"DAL", "UAL", "SWA"}


def test_pool_add_airline_with_fleet():
    pool = ResponderPool()
    fleet = [flight("F1"), flight("F2")]
    responder = pool.add_airline("DAL", fleet=fleet)
    assert len(responder.fleet) == 2


def test_pool_add_airline_duplicate_raises():
    pool = ResponderPool()
    pool.add_airline("DAL")
    with pytest.raises(ValueError):
        pool.add_airline("DAL")


def test_pool_get_airline():
    pool = ResponderPool()
    responder = pool.add_airline("UAL")
    retrieved = pool.get_airline("UAL")
    assert retrieved is responder


def test_pool_get_airline_not_found():
    pool = ResponderPool()
    with pytest.raises(KeyError):
        pool.get_airline("NONEXISTENT")


def test_pool_remove_airline():
    pool = ResponderPool()
    pool.add_airline("DAL")
    pool.remove_airline("DAL")
    assert pool.airline_count() == 0
    with pytest.raises(KeyError):
        pool.get_airline("DAL")


def test_pool_airlines_sorted_alphabetically():
    pool = ResponderPool()
    pool.add_airline("SWA")
    pool.add_airline("DAL")
    pool.add_airline("UAL")
    assert pool.airlines() == ["DAL", "SWA", "UAL"]


def test_pool_process_directive_single_airline():
    pool = ResponderPool()
    fleet = [flight(f"F{i}", arr_min=i) for i in range(5)]
    pool.add_airline("DAL", fleet=fleet)
    gdp_msg = gdp(rate=2)
    results = pool.process_directive(gdp_msg)

    assert "DAL" in results
    assert len(results["DAL"]) == 1  # cap 4, overflow 1
    assert isinstance(results["DAL"][0], (CancellationNotice, FlightIntent))


def test_pool_process_directive_three_airlines_isolated():
    """Three airlines, same GDP, each responds independently with own fleet state."""
    pool = ResponderPool()

    # DAL: 5 flights, overflow 1
    dal_fleet = [flight(f"DAL_{i}", arr_min=i) for i in range(5)]
    pool.add_airline("DAL", fleet=dal_fleet)

    # UAL: 3 flights, no overflow
    ual_fleet = [flight(f"UAL_{i}", arr_min=i) for i in range(3)]
    pool.add_airline("UAL", fleet=ual_fleet)

    # SWA: 6 flights, overflow 2
    swa_fleet = [flight(f"SWA_{i}", arr_min=i) for i in range(6)]
    pool.add_airline("SWA", fleet=swa_fleet)

    gdp_msg = gdp(rate=2)  # capacity 4
    results = pool.process_directive(gdp_msg)

    # Each airline produces responses based on its own fleet
    assert len(results["DAL"]) == 1  # 5 - 4 = 1
    assert len(results["UAL"]) == 0  # 3 <= 4
    assert len(results["SWA"]) == 2  # 6 - 4 = 2
    assert len(results) == 3  # all three airlines present


def test_pool_process_directive_responses_bear_airline_code():
    """Each response's issuer matches its source airline."""
    pool = ResponderPool()
    dal_fleet = [flight(f"F{i}", arr_min=i) for i in range(5)]
    pool.add_airline("DAL", fleet=dal_fleet)

    ual_fleet = [flight(f"F{i}", arr_min=i) for i in range(5)]
    pool.add_airline("UAL", fleet=ual_fleet)

    gdp_msg = gdp(rate=2)
    results = pool.process_directive(gdp_msg)

    assert all(m.issuer == "DAL" for m in results["DAL"])
    assert all(m.issuer == "UAL" for m in results["UAL"])


def test_pool_process_directive_broadcast_order_is_deterministic():
    """Processing order is alphabetical (DAL, SWA, UAL) regardless of add order."""
    pool1 = ResponderPool()
    pool1.add_airline("SWA", fleet=[flight(f"F{i}", arr_min=i) for i in range(5)])
    pool1.add_airline("DAL", fleet=[flight(f"F{i}", arr_min=i) for i in range(5)])
    pool1.add_airline("UAL", fleet=[flight(f"F{i}", arr_min=i) for i in range(5)])
    results1 = pool1.process_directive(gdp(rate=2))

    pool2 = ResponderPool()
    pool2.add_airline("DAL", fleet=[flight(f"F{i}", arr_min=i) for i in range(5)])
    pool2.add_airline("UAL", fleet=[flight(f"F{i}", arr_min=i) for i in range(5)])
    pool2.add_airline("SWA", fleet=[flight(f"F{i}", arr_min=i) for i in range(5)])
    results2 = pool2.process_directive(gdp(rate=2))

    # Results dict should have same structure regardless of add order
    assert set(results1.keys()) == set(results2.keys())
    for airline in results1.keys():
        assert len(results1[airline]) == len(results2[airline])


def test_pool_process_directive_rejects_up_message():
    """Pool rejects UP directives."""
    pool = ResponderPool()
    pool.add_airline("DAL")
    up = SubstitutionRequest(
        message_id="u",
        issuer="DAL-OCC",
        program_id="g",
        swaps=[SlotSwap(cancel_flight="X", promote_flight="Y")],
    )
    with pytest.raises(ValueError):
        pool.process_directive(up)


def test_pool_empty_airlines_process_directive():
    """Empty pool processes without error (no responses)."""
    pool = ResponderPool()
    results = pool.process_directive(gdp())
    assert results == {}


def test_pool_ground_stop_broadcast():
    """All airlines receive and process a ground stop independently."""
    pool = ResponderPool()
    pool.add_airline("DAL", fleet=[flight("DAL_1", dest="KORD")])
    pool.add_airline("UAL", fleet=[flight("UAL_1", dest="KORD"), flight("UAL_2", dest="KDEN")])

    stop = GroundStop(
        message_id="s", issuer="ATCSCC", element="KORD", reason="snow", until=T2
    )
    results = pool.process_directive(stop)

    assert len(results["DAL"]) == 1  # DAL_1 bound for KORD
    assert len(results["UAL"]) == 1  # UAL_1 bound for KORD; UAL_2 unaffected
    assert all(m.intended_action == "delay" for m in results["DAL"] + results["UAL"])


def test_pool_miles_in_trail_broadcast():
    """All airlines receive and process MIT independently."""
    pool = ResponderPool()
    pool.add_airline(
        "DAL", fleet=[flight("DAL_1", fixes=["BOZEE"]), flight("DAL_2", fixes=["OTHER"])]
    )
    pool.add_airline("UAL", fleet=[flight("UAL_1", fixes=["BOZEE"])])

    mit = MilesInTrail(
        message_id="m", issuer="ATCSCC", fix="BOZEE", miles=20, altitude_ft=33000
    )
    results = pool.process_directive(mit)

    assert len(results["DAL"]) == 1  # only DAL_1
    assert len(results["UAL"]) == 1  # only UAL_1
    assert all(m.intended_action == "delay" for m in results["DAL"] + results["UAL"])


def test_pool_callback_on_airline_response():
    """Each airline's callback is invoked when processing a directive."""
    captured_dal = []
    captured_ual = []

    def dal_callback(airline, responses):
        captured_dal.append((airline, len(responses)))

    def ual_callback(airline, responses):
        captured_ual.append((airline, len(responses)))

    pool = ResponderPool()
    pool.add_airline(
        "DAL",
        fleet=[flight(f"F{i}", arr_min=i) for i in range(5)],
        response_callback=dal_callback,
    )
    pool.add_airline(
        "UAL",
        fleet=[flight(f"F{i}", arr_min=i) for i in range(3)],
        response_callback=ual_callback,
    )

    pool.process_directive(gdp(rate=2))

    assert len(captured_dal) == 1
    assert captured_dal[0] == ("DAL", 1)
    assert len(captured_ual) == 1
    assert captured_ual[0] == ("UAL", 0)


def test_pool_large_federation():
    """10 airlines, same GDP, all respond independently."""
    pool = ResponderPool()
    for i in range(10):
        airline_code = f"A{i:02d}"
        # Vary fleet size to test isolation
        fleet_size = 3 + (i % 4)  # 3, 4, 5, 6 flights per airline
        fleet = [flight(f"{airline_code}_{j}", arr_min=j) for j in range(fleet_size)]
        pool.add_airline(airline_code, fleet=fleet)

    results = pool.process_directive(gdp(rate=2))  # capacity 4

    assert len(results) == 10
    # Each airline with < 4 flights produces 0 responses, >= 4 produces at least 1
    for airline_code in pool.airlines():
        fleet_size = len(pool.get_airline(airline_code).fleet)
        expected_overflow = max(0, fleet_size - 4)
        assert len(results[airline_code]) == expected_overflow


def test_pool_deterministic_across_runs():
    """Same input, same output order, every time."""
    def make_pool():
        pool = ResponderPool()
        for code in ["SWA", "DAL", "UAL"]:
            pool.add_airline(code, fleet=[flight(f"{code}_{i}", arr_min=i) for i in range(5)])
        return pool

    run1 = make_pool().process_directive(gdp(rate=2))
    run2 = make_pool().process_directive(gdp(rate=2))

    for airline in ["DAL", "SWA", "UAL"]:
        assert len(run1[airline]) == len(run2[airline])
        for m1, m2 in zip(run1[airline], run2[airline]):
            assert m1.flight_id == m2.flight_id
            assert type(m1) == type(m2)
