"""Seam translation tests — TFMProgram dict -> CDM wire message. No LLM, no network."""

from datetime import datetime, timedelta, timezone

import pytest

from cdm.messages import (
    CDMDirection,
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
)
from cdm.seam import tfm_to_cdm

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=2)


def _tfm(**over):
    base = {
        "program_id": "tfm-1",
        "tfm_type": "gdp",
        "affected_fix": "KDEN",
        "rate_per_hour": 30,
        "reason": "thunderstorms",
        "active": True,
    }
    base.update(over)
    return base


def test_gdp_translation_produces_ground_delay_program():
    msg = tfm_to_cdm(_tfm(), issuer="ATCSCC", message_id="m1", start=T0, end=T1)
    assert isinstance(msg, GroundDelayProgram)
    assert msg.element == "KDEN"
    assert msg.program_rate_per_hour == 30
    assert msg.reason == "thunderstorms"
    assert msg.direction == CDMDirection.DOWN


def test_gdp_requires_window():
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(), issuer="ATCSCC", message_id="m1")


def test_gdp_requires_end_too():
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(), issuer="ATCSCC", message_id="m1", start=T0)


def test_gdp_missing_rate_raises():
    tfm = _tfm()
    del tfm["rate_per_hour"]
    with pytest.raises(ValueError):
        tfm_to_cdm(tfm, issuer="ATCSCC", message_id="m1", start=T0, end=T1)


def test_gdp_invalid_window_propagates_validation_error():
    # end before start: the message model rejects it through the translator
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(), issuer="ATCSCC", message_id="m1", start=T1, end=T0)


def test_ground_stop_translation():
    msg = tfm_to_cdm(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                     issuer="ATCSCC", message_id="m2", until=T1)
    assert isinstance(msg, GroundStop)
    assert msg.element == "KORD"
    assert msg.until == T1


def test_ground_stop_requires_until():
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(tfm_type="ground_stop", affected_fix="KORD"),
                   issuer="ATCSCC", message_id="m2")


def test_miles_in_trail_translation():
    msg = tfm_to_cdm(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                     issuer="ATCSCC", message_id="m3", miles=20, altitude_ft=33000)
    assert isinstance(msg, MilesInTrail)
    assert msg.fix == "BOZEE"
    assert msg.miles == 20


def test_miles_in_trail_requires_miles_and_altitude():
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(tfm_type="miles_in_trail", affected_fix="BOZEE"),
                   issuer="ATCSCC", message_id="m3", miles=20)


def test_unknown_tfm_type_raises():
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(tfm_type="rocket_boost"), issuer="ATCSCC", message_id="m4")


def test_missing_reason_defaults_to_unspecified():
    tfm = _tfm()
    del tfm["reason"]
    msg = tfm_to_cdm(tfm, issuer="ATCSCC", message_id="m1", start=T0, end=T1)
    assert msg.reason == "(unspecified)"


def test_bad_airport_in_tfm_rejected_by_message_model():
    with pytest.raises(ValueError):
        tfm_to_cdm(_tfm(affected_fix="DEN"), issuer="ATCSCC", message_id="m1",
                   start=T0, end=T1)
