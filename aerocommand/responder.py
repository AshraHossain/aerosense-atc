"""AOC responder — deterministic airline reaction to CDM flow directives.

When ATC sends a DOWN directive (the airline *must* absorb it), the airline still
controls *how*: which of its own flights to delay, swap, or cancel. That collaborative
choice is the "C" in CDM. This module makes that choice with pure, deterministic rules
(no LLM), which is exactly what should be deterministic — a flow response must be
reproducible and auditable, not a model's mood.

Policy (intentionally simple and explainable — ponytail: rules a controller could read):
  - A Ground Delay Program meters arrivals at an airport. If the airline has more
    arrivals than the program's capacity allows, the lowest-priority flights are the
    "victims": cancellable ones are cancelled, the rest are delayed. Highest-priority
    flights are protected by construction.
  - A Ground Stop delays every affected arrival until the stop lifts.
  - Miles-in-Trail delays every flight whose route crosses the constrained fix.

Tie-break is always (priority, then flight_id) so the output is fully deterministic.
The responder reacts ONLY to DOWN messages; handing it an UP message is a programming
error and raises.
"""

from __future__ import annotations

from typing import Callable

from cdm.messages import (
    CDMDirection,
    CancellationNotice,
    FlightIntent,
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
    _CDMBase,
)
from aerocommand.fleet import FleetFlight


def _gdp_capacity(gdp: GroundDelayProgram) -> int:
    """Arrivals the program admits over its whole window (floored)."""
    hours = (gdp.end - gdp.start).total_seconds() / 3600.0
    return max(0, int(gdp.program_rate_per_hour * hours))


def _arrivals_for(flights: list[FleetFlight], element: str) -> list[FleetFlight]:
    affected = [f for f in flights if f.destination == element]
    return sorted(affected, key=lambda f: (f.scheduled_arrival, f.flight_id))


def respond_to_gdp(
    gdp: GroundDelayProgram, flights: list[FleetFlight], *, issuer: str = "AOC"
) -> list[_CDMBase]:
    """Cancel/delay the lowest-priority arrivals that exceed the GDP capacity."""
    affected = _arrivals_for(flights, gdp.element)
    capacity = _gdp_capacity(gdp)
    overflow = len(affected) - capacity
    if overflow <= 0:
        return []  # the whole fleet fits the program; nothing to give up

    # lowest priority first (tie-break flight_id) are the ones who absorb the cut
    victims = sorted(affected, key=lambda f: (f.priority, f.flight_id))[:overflow]
    out: list[_CDMBase] = []
    for v in victims:
        if v.cancellable:
            out.append(
                CancellationNotice(
                    message_id=f"{v.flight_id}-cxl",
                    issuer=issuer,
                    flight_id=v.flight_id,
                    reason=f"GDP {gdp.element}: arrival capacity {capacity}",
                )
            )
        else:
            out.append(
                FlightIntent(
                    message_id=f"{v.flight_id}-dly",
                    issuer=issuer,
                    flight_id=v.flight_id,
                    intended_action="delay",
                    details=f"GDP {gdp.element} (not cancellable)",
                )
            )
    return out


def respond_to_ground_stop(
    stop: GroundStop, flights: list[FleetFlight], *, issuer: str = "AOC"
) -> list[FlightIntent]:
    """Delay every arrival bound for the stopped element until it lifts."""
    return [
        FlightIntent(
            message_id=f"{f.flight_id}-gs",
            issuer=issuer,
            flight_id=f.flight_id,
            intended_action="delay",
            details=f"ground stop {stop.element} until {stop.until.isoformat()}",
        )
        for f in _arrivals_for(flights, stop.element)
    ]


def respond_to_miles_in_trail(
    mit: MilesInTrail, flights: list[FleetFlight], *, issuer: str = "AOC"
) -> list[FlightIntent]:
    """Delay every flight whose route crosses the constrained fix."""
    affected = [f for f in flights if mit.fix in f.route_fixes]
    affected.sort(key=lambda f: (f.scheduled_arrival, f.flight_id))
    return [
        FlightIntent(
            message_id=f"{f.flight_id}-mit",
            issuer=issuer,
            flight_id=f.flight_id,
            intended_action="delay",
            details=f"miles-in-trail {mit.miles} NM over {mit.fix}",
        )
        for f in affected
    ]


_DISPATCH: dict[type, Callable] = {
    GroundDelayProgram: respond_to_gdp,
    GroundStop: respond_to_ground_stop,
    MilesInTrail: respond_to_miles_in_trail,
}


def respond_to_directive(
    directive: _CDMBase, flights: list[FleetFlight], *, issuer: str = "AOC"
) -> list[_CDMBase]:
    """Route a DOWN directive to the matching responder.

    Raises ValueError on an UP message (the responder reacts, it does not receive
    its own replies) or an unrecognised directive type.
    """
    if directive.direction != CDMDirection.DOWN:
        raise ValueError(
            f"responder only reacts to DOWN directives, got {directive.direction}"
        )
    handler = _DISPATCH.get(type(directive))
    if handler is None:
        raise ValueError(f"no responder for directive type {type(directive).__name__}")
    return handler(directive, flights, issuer=issuer)
