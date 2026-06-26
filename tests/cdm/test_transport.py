"""In-memory CDM transport tests — FIFO, filtering, isolation. No LLM, no network."""

from datetime import datetime, timedelta, timezone

from cdm.messages import (
    CDMDirection,
    CDMMessageType,
    GroundDelayProgram,
    GroundStop,
    FlightIntent,
)
from cdm.transport import InMemoryCDMTransport

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=2)


def _gdp(mid="g1"):
    return GroundDelayProgram(message_id=mid, issuer="ATCSCC", element="KDEN",
                              program_rate_per_hour=30, start=T0, end=T1, reason="wx")


def _stop(mid="s1"):
    return GroundStop(message_id=mid, issuer="ATCSCC", element="KORD",
                      reason="snow", until=T1)


def _intent(mid="i1"):
    return FlightIntent(message_id=mid, issuer="DAL-OCC", flight_id="DAL1",
                        intended_action="continue")


def test_new_transport_is_empty():
    assert InMemoryCDMTransport().pending == 0


def test_publish_increments_pending():
    t = InMemoryCDMTransport()
    t.publish(_gdp())
    assert t.pending == 1
    assert len(t) == 1


def test_publish_many():
    t = InMemoryCDMTransport()
    t.publish_many([_gdp("a"), _gdp("b"), _gdp("c")])
    assert t.pending == 3


def test_drain_all_returns_everything_fifo():
    t = InMemoryCDMTransport()
    t.publish_many([_gdp("a"), _stop("b"), _intent("c")])
    drained = t.drain()
    assert [m.message_id for m in drained] == ["a", "b", "c"]


def test_drain_empties_the_queue():
    t = InMemoryCDMTransport()
    t.publish(_gdp())
    t.drain()
    assert t.pending == 0


def test_drain_on_empty_returns_empty_list():
    assert InMemoryCDMTransport().drain() == []


def test_drain_by_direction_down():
    t = InMemoryCDMTransport()
    t.publish_many([_gdp("a"), _intent("b"), _stop("c")])
    down = t.drain(direction=CDMDirection.DOWN)
    assert [m.message_id for m in down] == ["a", "c"]


def test_drain_by_direction_leaves_non_matching():
    t = InMemoryCDMTransport()
    t.publish_many([_gdp("a"), _intent("b"), _stop("c")])
    t.drain(direction=CDMDirection.DOWN)
    # the UP intent should remain
    assert t.pending == 1
    assert t.drain()[0].message_id == "b"


def test_drain_by_direction_up():
    t = InMemoryCDMTransport()
    t.publish_many([_gdp("a"), _intent("b")])
    up = t.drain(direction=CDMDirection.UP)
    assert [m.message_id for m in up] == ["b"]


def test_drain_by_message_type():
    t = InMemoryCDMTransport()
    t.publish_many([_gdp("a"), _stop("b"), _gdp("c")])
    gdps = t.drain(message_type=CDMMessageType.GROUND_DELAY_PROGRAM)
    assert [m.message_id for m in gdps] == ["a", "c"]
    assert t.pending == 1  # the ground stop remains


def test_drain_preserves_order_of_kept_messages():
    t = InMemoryCDMTransport()
    t.publish_many([_stop("a"), _gdp("b"), _stop("c"), _gdp("d")])
    t.drain(message_type=CDMMessageType.GROUND_DELAY_PROGRAM)
    remaining = t.drain()
    assert [m.message_id for m in remaining] == ["a", "c"]


def test_two_transports_are_isolated():
    a, b = InMemoryCDMTransport(), InMemoryCDMTransport()
    a.publish(_gdp())
    assert a.pending == 1 and b.pending == 0


def test_drain_filter_matching_nothing_keeps_all():
    t = InMemoryCDMTransport()
    t.publish_many([_intent("a"), _intent("b")])
    got = t.drain(direction=CDMDirection.DOWN)
    assert got == []
    assert t.pending == 2
