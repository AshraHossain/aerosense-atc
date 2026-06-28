"""AeroCommand — the airline Operations Control Center (AOC) app.

The airline side of the AeroOps platform. Consumes CDM flow directives from
AeroSense (ATC) and produces the collaborative responses the airline retains
authority over (which flights to delay, swap, or cancel).

Five phases of multi-airline federation:
  M5 Phase 1: FleetFlight & deterministic responder (responder.py)
  M5 Phase 2: Per-airline responder isolation (responder_pool.py)
  M5 Phase 3: Cross-airline swap arbitration (slot_negotiation.py)
  M5 Phase 4: Percentage-based capacity fairness (fair_allocation.py)
  M5 Phase 5: E2E integration with 3+ airlines (tests/multiairline_scenario.py)

Depends only on the shared `cdm/` package — never on `core/` or `aerosense/` —
so it can be tested in isolation and will not collide with the evolving ATC-side
code. The LLM-driven AOC agents (crew/maintenance/passenger/finance/compliance,
full M3) layer on top later.
"""

from aerocommand.fleet import FleetFlight
from aerocommand.responder import (
    respond_to_directive,
    respond_to_gdp,
    respond_to_ground_stop,
    respond_to_miles_in_trail,
)
from aerocommand.responder_pool import ResponderPool, AirlineResponder
from aerocommand.slot_negotiation import SlotNegotiator, SwapProposal, SwapDecision
from aerocommand.fair_allocation import FairAllocator, AllocationQuota, AllocationPlan

__all__ = [
    # Phase 1: Core responder
    "FleetFlight",
    "respond_to_directive",
    "respond_to_gdp",
    "respond_to_ground_stop",
    "respond_to_miles_in_trail",
    # Phase 2: Per-airline isolation
    "AirlineResponder",
    "ResponderPool",
    # Phase 3: Cross-airline negotiation
    "SlotNegotiator",
    "SwapProposal",
    "SwapDecision",
    # Phase 4: Fair capacity allocation
    "FairAllocator",
    "AllocationQuota",
    "AllocationPlan",
]
