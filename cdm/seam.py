"""Seam translation — ATC-internal TFM program -> CDM wire message.

AeroSense's Phase 10 produces `TFMProgram` entries inside `ATCState` (a TypedDict,
i.e. a plain dict at runtime). When a program must be communicated to the airline,
it is translated here into a validated CDM `DOWN` message.

`tfm_to_cdm` takes a plain dict, not a `core` import, so this module stays a leaf and
will not conflict with the evolving `core/` package. The internal `TFMProgram` does
not carry every wire field (a GDP needs a start/end window; a ground stop needs an
`until`; miles-in-trail needs spacing + altitude), so those are required as explicit
context arguments — translating without them would be guessing, and a flow directive
is not a place to guess.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from cdm.messages import (
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
    _CDMBase,
)


def tfm_to_cdm(
    tfm: dict,
    *,
    issuer: str,
    message_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    until: Optional[datetime] = None,
    miles: Optional[float] = None,
    altitude_ft: Optional[int] = None,
) -> _CDMBase:
    """Translate one ATCState `TFMProgram` dict into a CDM DOWN message.

    Raises ValueError on an unknown `tfm_type` or missing per-type context.
    """
    tfm_type = tfm.get("tfm_type")
    element_or_fix = tfm.get("affected_fix", "")
    reason = tfm.get("reason", "") or "(unspecified)"

    if tfm_type == "gdp":
        if start is None or end is None:
            raise ValueError("gdp translation requires start and end")
        rate = tfm.get("rate_per_hour")
        if rate is None:
            raise ValueError("gdp translation requires rate_per_hour on the program")
        return GroundDelayProgram(
            message_id=message_id,
            issuer=issuer,
            element=element_or_fix,
            program_rate_per_hour=rate,
            start=start,
            end=end,
            reason=reason,
        )

    if tfm_type == "ground_stop":
        if until is None:
            raise ValueError("ground_stop translation requires until")
        return GroundStop(
            message_id=message_id,
            issuer=issuer,
            element=element_or_fix,
            reason=reason,
            until=until,
        )

    if tfm_type == "miles_in_trail":
        if miles is None or altitude_ft is None:
            raise ValueError(
                "miles_in_trail translation requires miles and altitude_ft"
            )
        return MilesInTrail(
            message_id=message_id,
            issuer=issuer,
            fix=element_or_fix,
            miles=miles,
            altitude_ft=altitude_ft,
        )

    raise ValueError(f"unknown tfm_type: {tfm_type!r}")
