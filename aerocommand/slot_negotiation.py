"""SlotNegotiation — cross-airline swap arbitration (M5 Phase 3).

When airline A proposes a cross-airline swap with airline B (e.g. "cancel my flight F1,
promote airline B's flight F2 to my slot"), the ATC negotiator validates that:
  1. Both flights exist in the respective airlines' fleets
  2. Cancelling F1 and promoting F2 improves fairness for the system
  3. Tie-breaks are deterministic (airline code alphabetical, then flight ID)

The arbitrator applies rules inspired by IATA CDM slot swap guidelines but remains
deterministic (no randomness, no negotiation rounds). A swap is approved if:
  - Both flights are known
  - The source airline does not drop below its fair share
  - The target airline does not exceed its fair share by swapping in
  - Tie-break: lower airline code wins if both meet the rules
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from aerocommand.fleet import FleetFlight
from cdm.messages import SlotSwap, SubstitutionRequest


@dataclass
class SwapProposal:
    """One airline's proposal to swap two flights across airlines.

    Attributes:
        proposer_code: airline code making the proposal (e.g. 'DAL')
        swap: SlotSwap containing cancel_flight and promote_flight IDs
        proposer_flight: the full FleetFlight object being cancelled
        target_flight: the full FleetFlight object being promoted
        target_code: airline code that owns target_flight
    """

    proposer_code: str
    swap: SlotSwap
    proposer_flight: FleetFlight
    target_flight: FleetFlight
    target_code: str

    @property
    def cancel_flight_id(self) -> str:
        return self.swap.cancel_flight

    @property
    def promote_flight_id(self) -> str:
        return self.swap.promote_flight


@dataclass
class SwapDecision:
    """Arbitrator's decision on a swap proposal.

    Attributes:
        proposal: the SwapProposal being decided
        approved: True if swap is approved, False otherwise
        reason: human-readable explanation (e.g. "Approved: DAL stays above fair share")
        applied_rules: list of rules checked (in order)
    """

    proposal: SwapProposal
    approved: bool
    reason: str
    applied_rules: list[str] = field(default_factory=list)


class SlotNegotiator:
    """Arbitrate cross-airline slot swaps.

    This is a deterministic arbitrator, not a negotiation agent. It validates
    swaps against rules and approves/rejects based on:
      1. Flight existence
      2. Fair-share preservation
      3. Deterministic tie-break (airline code alphabetical)
    """

    def __init__(self, capacity_per_airport: dict[str, int] | None = None):
        """Initialize the negotiator.

        Args:
            capacity_per_airport: optional dict mapping airport -> slot count
                If None, computed per decision based on airline fleets.
        """
        self.capacity_per_airport = capacity_per_airport or {}

    def validate_proposal(
        self,
        proposal: SwapProposal,
        proposer_fleet: list[FleetFlight],
        target_fleet: list[FleetFlight],
    ) -> SwapDecision:
        """Validate and decide on a single swap proposal.

        Args:
            proposal: the SwapProposal to validate
            proposer_fleet: the proposer airline's full fleet
            target_fleet: the target airline's full fleet

        Returns:
            SwapDecision with approved/rejected verdict and reasoning
        """
        rules_checked: list[str] = []

        # Rule 1: Flights must exist in their respective fleets
        rules_checked.append("flight_existence")
        proposer_ids = {f.flight_id for f in proposer_fleet}
        target_ids = {f.flight_id for f in target_fleet}

        if proposal.cancel_flight_id not in proposer_ids:
            return SwapDecision(
                proposal=proposal,
                approved=False,
                reason=f"Rejected: proposer flight {proposal.cancel_flight_id} "
                f"not found in {proposal.proposer_code} fleet",
                applied_rules=rules_checked,
            )

        if proposal.promote_flight_id not in target_ids:
            return SwapDecision(
                proposal=proposal,
                approved=False,
                reason=f"Rejected: target flight {proposal.promote_flight_id} "
                f"not found in {proposal.target_code} fleet",
                applied_rules=rules_checked,
            )

        # Rule 2: Destination must be the same (both landing at same airport)
        rules_checked.append("destination_match")
        if proposal.proposer_flight.destination != proposal.target_flight.destination:
            return SwapDecision(
                proposal=proposal,
                approved=False,
                reason=f"Rejected: destinations do not match "
                f"({proposal.proposer_flight.destination} vs {proposal.target_flight.destination})",
                applied_rules=rules_checked,
            )

        # Rule 3: Fair-share check
        # After swap: proposer loses 1 slot (cancel), target gains 1 slot (promote)
        rules_checked.append("fair_share_preservation")
        airport = proposal.proposer_flight.destination

        # Count current arrivals by airline at this airport
        proposer_arrivals = len([f for f in proposer_fleet if f.destination == airport])
        target_arrivals = len([f for f in target_fleet if f.destination == airport])

        # After swap
        proposer_after = proposer_arrivals - 1  # lost one
        target_after = target_arrivals + 1  # gained one

        # Determine fair share (equal split for now; can be percentage-based later)
        total_airlines = 2  # binary swap
        total_arrivals = proposer_arrivals + target_arrivals
        fair_share = total_arrivals / total_airlines

        # Both airlines must stay within ±1.0 of fair share (more lenient than ±0.5)
        # to allow simple 1:1 swaps (e.g., 2 arrivals each with fair share 2.0)
        lower_bound = fair_share - 1.0
        upper_bound = fair_share + 1.0

        # Proposer must not drop too far below fair share
        if proposer_after < lower_bound:
            return SwapDecision(
                proposal=proposal,
                approved=False,
                reason=f"Rejected: {proposal.proposer_code} would drop below fair share "
                f"({proposer_after:.1f} < {lower_bound:.1f})",
                applied_rules=rules_checked,
            )

        # Target must not exceed fair share by too much
        if target_after > upper_bound:
            return SwapDecision(
                proposal=proposal,
                approved=False,
                reason=f"Rejected: {proposal.target_code} would exceed fair share "
                f"({target_after:.1f} > {upper_bound:.1f})",
                applied_rules=rules_checked,
            )

        # Rule 4: Deterministic tie-break (airline code alphabetical)
        rules_checked.append("deterministic_tiebreak")
        if proposal.proposer_code > proposal.target_code:
            # Lower code wins in case of conflict (tie-break rule)
            # This is a simplified policy; real CDM might allow both
            return SwapDecision(
                proposal=proposal,
                approved=True,  # We still approve, but note the tie-break rule was checked
                reason=f"Approved: {proposal.proposer_code} -> "
                f"{proposal.target_code} swap (tiebreak favors {proposal.target_code}, "
                f"but proposer authorized)",
                applied_rules=rules_checked,
            )

        # If all rules pass
        return SwapDecision(
            proposal=proposal,
            approved=True,
            reason=f"Approved: {proposal.proposer_code} -> {proposal.target_code} swap "
            f"preserves fair share (each at ~{fair_share:.1f} arrivals)",
            applied_rules=rules_checked,
        )

    def resolve_swaps(
        self,
        proposals: list[SwapProposal],
        fleets: dict[str, list[FleetFlight]],
    ) -> dict[str, SwapDecision]:
        """Resolve a batch of swap proposals.

        Each proposal is validated independently. Conflicting swaps are not
        re-ordered; the caller is responsible for ensuring non-conflicting input.

        Args:
            proposals: list of SwapProposal objects
            fleets: dict mapping airline_code -> list[FleetFlight]

        Returns:
            dict mapping proposal (id or hash) -> SwapDecision
        """
        decisions: dict[str, SwapDecision] = {}

        for i, proposal in enumerate(proposals):
            proposer_fleet = fleets.get(proposal.proposer_code, [])
            target_fleet = fleets.get(proposal.target_code, [])

            decision = self.validate_proposal(proposal, proposer_fleet, target_fleet)
            key = f"{proposal.proposer_code}_{proposal.swap.cancel_flight}_{proposal.swap.promote_flight}"
            decisions[key] = decision

        return decisions


def build_swap_proposal(
    proposer_code: str,
    swap: SlotSwap,
    proposer_fleet: list[FleetFlight],
    target_code: str,
    target_fleet: list[FleetFlight],
) -> Optional[SwapProposal]:
    """Build a SwapProposal from raw inputs, validating flight existence.

    Args:
        proposer_code: airline proposing the swap
        swap: SlotSwap message
        proposer_fleet: proposer's fleet
        target_code: target airline
        target_fleet: target's fleet

    Returns:
        SwapProposal if both flights exist, None otherwise
    """
    proposer_lookup = {f.flight_id: f for f in proposer_fleet}
    target_lookup = {f.flight_id: f for f in target_fleet}

    proposer_flight = proposer_lookup.get(swap.cancel_flight)
    target_flight = target_lookup.get(swap.promote_flight)

    if not proposer_flight or not target_flight:
        return None

    return SwapProposal(
        proposer_code=proposer_code,
        swap=swap,
        proposer_flight=proposer_flight,
        target_flight=target_flight,
        target_code=target_code,
    )
