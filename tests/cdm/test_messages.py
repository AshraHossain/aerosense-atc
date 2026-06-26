"""CDM message contract tests — validation at the trust boundary, no LLM, no network."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from cdm.messages import (
    CDMDirection,
    CDMMessageType,
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
    SlotSwap,
    SubstitutionRequest,
    FlightIntent,
    CancellationNotice,
    DOWN_MESSAGE_TYPES,
    UP_MESSAGE_TYPES,
)

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=2)


def _gdp(**over):
    kw = dict(
        message_id="m1", issuer="ATCSCC", element="KDEN",
        program_rate_per_hour=30, start=T0, end=T1, reason="weather",
    )
    kw.update(over)
    return GroundDelayProgram(**kw)


# ── direction is derived, never trusted ────────────────────────────────────────

def test_gdp_direction_is_down():
    assert _gdp().direction == CDMDirection.DOWN


def test_ground_stop_direction_is_down():
    assert GroundStop(message_id="m", issuer="ATCSCC", element="KORD",
                      reason="snow", until=T1).direction == CDMDirection.DOWN


def test_miles_in_trail_direction_is_down():
    assert MilesInTrail(message_id="m", issuer="ATCSCC", fix="BOZEE",
                        miles=20, altitude_ft=33000).direction == CDMDirection.DOWN


def test_substitution_direction_is_up():
    msg = SubstitutionRequest(message_id="m", issuer="DAL-OCC", program_id="m1",
                              swaps=[SlotSwap(cancel_flight="DAL9", promote_flight="DAL1")])
    assert msg.direction == CDMDirection.UP


def test_flight_intent_direction_is_up():
    assert FlightIntent(message_id="m", issuer="DAL-OCC", flight_id="DAL1",
                        intended_action="continue").direction == CDMDirection.UP


def test_cancellation_direction_is_up():
    assert CancellationNotice(message_id="m", issuer="DAL-OCC", flight_id="DAL9",
                              reason="crew").direction == CDMDirection.UP


def test_down_and_up_sets_partition_all_types():
    assert DOWN_MESSAGE_TYPES.isdisjoint(UP_MESSAGE_TYPES)
    assert DOWN_MESSAGE_TYPES | UP_MESSAGE_TYPES == set(CDMMessageType)


def test_message_type_default_is_fixed():
    assert _gdp().message_type == CDMMessageType.GROUND_DELAY_PROGRAM


def test_wrong_message_type_literal_rejected():
    with pytest.raises(ValidationError):
        _gdp(message_type=CDMMessageType.GROUND_STOP)


# ── GDP validation ─────────────────────────────────────────────────────────────

def test_gdp_rate_must_be_positive():
    with pytest.raises(ValidationError):
        _gdp(program_rate_per_hour=0)


def test_gdp_negative_rate_rejected():
    with pytest.raises(ValidationError):
        _gdp(program_rate_per_hour=-5)


def test_gdp_end_after_start_required():
    with pytest.raises(ValidationError):
        _gdp(start=T1, end=T0)


def test_gdp_equal_start_end_rejected():
    with pytest.raises(ValidationError):
        _gdp(start=T0, end=T0)


def test_gdp_bad_airport_code_rejected():
    with pytest.raises(ValidationError):
        _gdp(element="DEN")  # 3 letters, not ICAO


def test_gdp_lowercase_airport_rejected():
    with pytest.raises(ValidationError):
        _gdp(element="kden")


def test_gdp_valid_affected_origins():
    msg = _gdp(affected_origins=["KSFO", "KLAX"])
    assert msg.affected_origins == ["KSFO", "KLAX"]


def test_gdp_bad_affected_origin_rejected():
    with pytest.raises(ValidationError):
        _gdp(affected_origins=["KSFO", "LAX"])


def test_gdp_empty_reason_rejected():
    with pytest.raises(ValidationError):
        _gdp(reason="")


def test_gdp_extra_field_forbidden():
    with pytest.raises(ValidationError):
        _gdp(unexpected="x")


# ── GroundStop / MilesInTrail validation ───────────────────────────────────────

def test_ground_stop_requires_valid_airport():
    with pytest.raises(ValidationError):
        GroundStop(message_id="m", issuer="ATCSCC", element="ORD",
                   reason="snow", until=T1)


def test_ground_stop_empty_reason_rejected():
    with pytest.raises(ValidationError):
        GroundStop(message_id="m", issuer="ATCSCC", element="KORD",
                   reason="", until=T1)


def test_miles_in_trail_miles_positive():
    with pytest.raises(ValidationError):
        MilesInTrail(message_id="m", issuer="ATCSCC", fix="BOZEE",
                     miles=0, altitude_ft=33000)


def test_miles_in_trail_negative_altitude_rejected():
    with pytest.raises(ValidationError):
        MilesInTrail(message_id="m", issuer="ATCSCC", fix="BOZEE",
                     miles=20, altitude_ft=-1)


def test_miles_in_trail_accepts_fix_and_airport_like_fix():
    assert MilesInTrail(message_id="m", issuer="ATCSCC", fix="J12",
                        miles=15, altitude_ft=0).fix == "J12"


def test_miles_in_trail_bad_fix_rejected():
    with pytest.raises(ValidationError):
        MilesInTrail(message_id="m", issuer="ATCSCC", fix="toolongfix",
                     miles=15, altitude_ft=10000)


# ── SlotSwap / SubstitutionRequest ─────────────────────────────────────────────

def test_slot_swap_distinct_flights_required():
    with pytest.raises(ValidationError):
        SlotSwap(cancel_flight="DAL1", promote_flight="DAL1")


def test_slot_swap_valid():
    s = SlotSwap(cancel_flight="DAL9", promote_flight="DAL1")
    assert s.cancel_flight == "DAL9"


def test_substitution_requires_at_least_one_swap():
    with pytest.raises(ValidationError):
        SubstitutionRequest(message_id="m", issuer="DAL-OCC", program_id="m1", swaps=[])


def test_substitution_empty_program_id_rejected():
    with pytest.raises(ValidationError):
        SubstitutionRequest(message_id="m", issuer="DAL-OCC", program_id="",
                            swaps=[SlotSwap(cancel_flight="DAL9", promote_flight="DAL1")])


# ── FlightIntent ───────────────────────────────────────────────────────────────

def test_flight_intent_action_enum_enforced():
    with pytest.raises(ValidationError):
        FlightIntent(message_id="m", issuer="DAL-OCC", flight_id="DAL1",
                     intended_action="teleport")


def test_flight_intent_divert_requires_details():
    with pytest.raises(ValidationError):
        FlightIntent(message_id="m", issuer="DAL-OCC", flight_id="DAL1",
                     intended_action="divert")


def test_flight_intent_divert_with_details_ok():
    msg = FlightIntent(message_id="m", issuer="DAL-OCC", flight_id="DAL1",
                       intended_action="divert", details="KSLC")
    assert msg.details == "KSLC"


@pytest.mark.parametrize("action", ["continue", "delay", "cancel"])
def test_flight_intent_non_divert_actions_need_no_details(action):
    assert FlightIntent(message_id="m", issuer="DAL-OCC", flight_id="DAL1",
                        intended_action=action).intended_action == action


# ── envelope + serialization ───────────────────────────────────────────────────

def test_empty_message_id_rejected():
    with pytest.raises(ValidationError):
        _gdp(message_id="")


def test_empty_issuer_rejected():
    with pytest.raises(ValidationError):
        _gdp(issuer="")


def test_issued_at_autopopulates():
    assert isinstance(_gdp().issued_at, datetime)


def test_json_round_trip_preserves_fields():
    msg = _gdp()
    restored = GroundDelayProgram.model_validate_json(msg.model_dump_json())
    assert restored.element == "KDEN"
    assert restored.program_rate_per_hour == 30
    assert restored.direction == CDMDirection.DOWN


def test_json_round_trip_substitution():
    msg = SubstitutionRequest(message_id="m", issuer="DAL-OCC", program_id="m1",
                              swaps=[SlotSwap(cancel_flight="DAL9", promote_flight="DAL1")])
    restored = SubstitutionRequest.model_validate_json(msg.model_dump_json())
    assert restored.swaps[0].promote_flight == "DAL1"
