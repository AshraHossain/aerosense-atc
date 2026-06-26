"""Fleet model — the airline's view of its own flights, used by the AOC responder.

A `FleetFlight` is what the airline knows about one of its flights when a flow
directive arrives: where it's going, when it's due, how important it is to protect,
whether it may be cancelled, and which fixes its route crosses (for miles-in-trail).

Validated (Pydantic) because the responder makes cancel/delay decisions off these
fields — a bad airport code or a negative priority must fail at the door, not skew a
slot-allocation decision downstream.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_ICAO_AIRPORT = re.compile(r"^[A-Z]{4}$")
_FIX = re.compile(r"^[A-Z0-9]{2,5}$")


class FleetFlight(BaseModel):
    flight_id: str = Field(..., min_length=1)
    origin: str
    destination: str
    scheduled_arrival: datetime
    priority: int = Field(0, ge=0, description="higher = more important to protect")
    cancellable: bool = True
    route_fixes: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    @field_validator("origin", "destination")
    @classmethod
    def _v_airport(cls, v: str) -> str:
        if not _ICAO_AIRPORT.match(v):
            raise ValueError(f"not a valid 4-letter ICAO airport code: {v!r}")
        return v

    @field_validator("route_fixes")
    @classmethod
    def _v_fixes(cls, v: list[str]) -> list[str]:
        for fix in v:
            if not _FIX.match(fix):
                raise ValueError(f"not a valid fix identifier: {fix!r}")
        return v
