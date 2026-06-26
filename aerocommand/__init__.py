"""AeroCommand — the airline Operations Control Center (AOC) app.

The airline side of the AeroOps platform. Consumes CDM flow directives from
AeroSense (ATC) and produces the collaborative responses the airline retains
authority over (which flights to delay, swap, or cancel).

This first slice is the deterministic CDM responder (`aerocommand.responder`) and
its fleet model (`aerocommand.fleet`). It depends only on the shared `cdm/`
package — never on `core/` or `aerosense/` — so it can be tested in isolation and
will not collide with the evolving ATC-side code. The LLM-driven AOC agents
(crew/maintenance/passenger/finance/compliance, full M3) layer on top later.
"""

from aerocommand.fleet import FleetFlight
from aerocommand.responder import (
    respond_to_directive,
    respond_to_gdp,
    respond_to_ground_stop,
    respond_to_miles_in_trail,
)

__all__ = [
    "FleetFlight",
    "respond_to_directive",
    "respond_to_gdp",
    "respond_to_ground_stop",
    "respond_to_miles_in_trail",
]
