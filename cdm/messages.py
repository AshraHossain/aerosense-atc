"""CDM message contract — validated Pydantic models for the AeroSense<->AeroCommand seam.

Two directions, mirroring the real FAA<->airline CDM protocol:

  DOWN — flow *authority* (ATC/ATCSCC -> airline AOC). The airline must absorb these:
    GroundDelayProgram, GroundStop, MilesInTrail.

  UP — *collaboration* (airline AOC -> ATC). The airline retains control of its own
    fleet and responds with these:
    SubstitutionRequest, FlightIntent, CancellationNotice.

Every message validates at construction because the seam is a trust boundary —
a malformed GDP rate or a bad airport code must fail loudly here, not silently
corrupt a downstream reroute. Each model carries its own `message_type` and the
`direction` is derived from the type, so a message can never claim the wrong
direction.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ICAO airport identifiers are exactly 4 uppercase letters (e.g. KDEN, EGLL).
# Named fixes/waypoints are 2–5 uppercase alphanumerics (e.g. DEN, BOZEE, J12).
_ICAO_AIRPORT = re.compile(r"^[A-Z]{4}$")
_FIX = re.compile(r"^[A-Z0-9]{2,5}$")


class CDMDirection(str, Enum):
    DOWN = "down"  # flow authority: ATC -> AOC
    UP = "up"      # collaboration: AOC -> ATC


class CDMMessageType(str, Enum):
    GROUND_DELAY_PROGRAM = "ground_delay_program"
    GROUND_STOP = "ground_stop"
    MILES_IN_TRAIL = "miles_in_trail"
    SUBSTITUTION_REQUEST = "substitution_request"
    FLIGHT_INTENT = "flight_intent"
    CANCELLATION_NOTICE = "cancellation_notice"


DOWN_MESSAGE_TYPES: frozenset[CDMMessageType] = frozenset(
    {
        CDMMessageType.GROUND_DELAY_PROGRAM,
        CDMMessageType.GROUND_STOP,
        CDMMessageType.MILES_IN_TRAIL,
    }
)
UP_MESSAGE_TYPES: frozenset[CDMMessageType] = frozenset(
    {
        CDMMessageType.SUBSTITUTION_REQUEST,
        CDMMessageType.FLIGHT_INTENT,
        CDMMessageType.CANCELLATION_NOTICE,
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _CDMBase(BaseModel):
    """Common envelope. `direction` is computed from `message_type`, never trusted
    from input, so a message physically cannot misreport its direction."""

    message_id: str = Field(..., min_length=1)
    issuer: str = Field(..., min_length=1)  # e.g. "ATCSCC", "DAL-OCC"
    issued_at: datetime = Field(default_factory=_utcnow)

    model_config = {"extra": "forbid"}

    @property
    def direction(self) -> CDMDirection:
        # `message_type` is a Literal field on every concrete subclass; this base
        # is never instantiated directly, so the attribute always resolves.
        return (
            CDMDirection.DOWN
            if self.message_type in DOWN_MESSAGE_TYPES
            else CDMDirection.UP
        )


def _validate_airport(v: str) -> str:
    if not _ICAO_AIRPORT.match(v):
        raise ValueError(f"not a valid 4-letter ICAO airport code: {v!r}")
    return v


def _validate_fix(v: str) -> str:
    if not _FIX.match(v):
        raise ValueError(f"not a valid fix/waypoint identifier: {v!r}")
    return v


# ── DOWN: flow authority (ATC -> AOC) ──────────────────────────────────────────

class GroundDelayProgram(_CDMBase):
    """A GDP meters arrivals into a constrained airport by assigning a max arrival
    rate. The airline must delay/absorb flights to fit the rate."""

    message_type: Literal[CDMMessageType.GROUND_DELAY_PROGRAM] = (
        CDMMessageType.GROUND_DELAY_PROGRAM
    )
    element: str = Field(..., description="constrained airport (ICAO)")
    program_rate_per_hour: int = Field(..., gt=0, description="max arrivals/hour")
    start: datetime
    end: datetime
    affected_origins: list[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=1)

    _v_element = field_validator("element")(_validate_airport)

    @field_validator("affected_origins")
    @classmethod
    def _v_origins(cls, v: list[str]) -> list[str]:
        for o in v:
            _validate_airport(o)
        return v

    @model_validator(mode="after")
    def _v_window(self) -> "GroundDelayProgram":
        if self.end <= self.start:
            raise ValueError("GDP end must be after start")
        return self


class GroundStop(_CDMBase):
    """A ground stop halts all departures bound for an element until a time."""

    message_type: Literal[CDMMessageType.GROUND_STOP] = CDMMessageType.GROUND_STOP
    element: str = Field(..., description="destination airport held for (ICAO)")
    reason: str = Field(..., min_length=1)
    until: datetime

    _v_element = field_validator("element")(_validate_airport)


class MilesInTrail(_CDMBase):
    """Miles-in-trail imposes a spacing (in NM) over a fix at an altitude."""

    message_type: Literal[CDMMessageType.MILES_IN_TRAIL] = (
        CDMMessageType.MILES_IN_TRAIL
    )
    fix: str
    miles: float = Field(..., gt=0)
    altitude_ft: int = Field(..., ge=0)

    _v_fix = field_validator("fix")(_validate_fix)


# ── UP: collaboration (AOC -> ATC) ─────────────────────────────────────────────

class SlotSwap(BaseModel):
    """Within a GDP, the airline may swap its own slots — protect a high-value
    flight by absorbing the delay on a lower-value one it cancels/delays."""

    cancel_flight: str = Field(..., min_length=1)
    promote_flight: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _v_distinct(self) -> "SlotSwap":
        if self.cancel_flight == self.promote_flight:
            raise ValueError("cancel_flight and promote_flight must differ")
        return self


class SubstitutionRequest(_CDMBase):
    """Airline's response to a GDP: a set of intra-fleet slot swaps it requests."""

    message_type: Literal[CDMMessageType.SUBSTITUTION_REQUEST] = (
        CDMMessageType.SUBSTITUTION_REQUEST
    )
    program_id: str = Field(..., min_length=1, description="the GDP message_id")
    swaps: list[SlotSwap] = Field(..., min_length=1)


class FlightIntent(_CDMBase):
    """Airline declares what it intends to do with a flight under the directive."""

    message_type: Literal[CDMMessageType.FLIGHT_INTENT] = (
        CDMMessageType.FLIGHT_INTENT
    )
    flight_id: str = Field(..., min_length=1)
    intended_action: Literal["continue", "delay", "divert", "cancel"]
    details: str = ""

    @model_validator(mode="after")
    def _v_divert(self) -> "FlightIntent":
        if self.intended_action == "divert" and not self.details:
            raise ValueError("divert intent requires details (alternate airport)")
        return self


class CancellationNotice(_CDMBase):
    """Airline notifies ATC that a flight is cancelled and its slot freed."""

    message_type: Literal[CDMMessageType.CANCELLATION_NOTICE] = (
        CDMMessageType.CANCELLATION_NOTICE
    )
    flight_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
