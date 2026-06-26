"""FleetFlight validation tests. No LLM, no network."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aerocommand.fleet import FleetFlight

A = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)


def _ff(**over):
    kw = dict(flight_id="DAL1", origin="KSFO", destination="KDEN",
              scheduled_arrival=A)
    kw.update(over)
    return FleetFlight(**kw)


def test_minimal_valid_flight():
    f = _ff()
    assert f.flight_id == "DAL1"
    assert f.priority == 0          # default
    assert f.cancellable is True    # default
    assert f.route_fixes == []      # default


def test_empty_flight_id_rejected():
    with pytest.raises(ValidationError):
        _ff(flight_id="")


def test_bad_origin_rejected():
    with pytest.raises(ValidationError):
        _ff(origin="SFO")


def test_bad_destination_rejected():
    with pytest.raises(ValidationError):
        _ff(destination="den")


def test_negative_priority_rejected():
    with pytest.raises(ValidationError):
        _ff(priority=-1)


def test_zero_priority_allowed():
    assert _ff(priority=0).priority == 0


def test_high_priority_allowed():
    assert _ff(priority=99).priority == 99


def test_cancellable_flag_settable():
    assert _ff(cancellable=False).cancellable is False


def test_route_fixes_valid():
    assert _ff(route_fixes=["BOZEE", "J12"]).route_fixes == ["BOZEE", "J12"]


def test_route_fixes_bad_identifier_rejected():
    with pytest.raises(ValidationError):
        _ff(route_fixes=["toolongfix"])


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        _ff(surprise="x")


def test_missing_scheduled_arrival_rejected():
    with pytest.raises(ValidationError):
        FleetFlight(flight_id="DAL1", origin="KSFO", destination="KDEN")


def test_json_round_trip():
    f = _ff(priority=5, route_fixes=["BOZEE"])
    restored = FleetFlight.model_validate_json(f.model_dump_json())
    assert restored.priority == 5
    assert restored.route_fixes == ["BOZEE"]
