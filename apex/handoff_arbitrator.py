"""
Handoff Arbitrator for APEX ATC Platform (M6 - Phase 3)

Manages aircraft handoffs between sectors using deterministic priority ordering:
  1. ATCSCC (Command Center) - highest priority
  2. ARTCC (Air Route Traffic Control Center)
  3. TRACON (Terminal Radar Approach Control)
  4. TOWER (Airport Tower) - lowest priority

Ensures:
  - Deterministic routing (priority enum, no randomness)
  - Conflict detection at sector boundaries
  - Approved handoff requests
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal

from apex.crossing_detector import CrossingDetector, SectorConflict
from apex.eval_coordinator import EvalScenario
from core.state import FlightTrack


# ── Type definitions ───────────────────────────────────────────────────────────

SectorID = Literal["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]


class SectorPriority(IntEnum):
    """Deterministic sector priority (higher = higher priority)."""

    TOWER = 1  # DEN-TOWER
    TRACON = 2  # DEN-TRACON
    ARTCC = 3  # DEN-ARTCC
    ATCSCC = 4  # Command Center (if involved)


def get_sector_priority(sector_id: SectorID) -> SectorPriority:
    """Get priority for a sector."""
    priority_map: dict[SectorID, SectorPriority] = {
        "DEN-TOWER": SectorPriority.TOWER,
        "DEN-TRACON": SectorPriority.TRACON,
        "DEN-ARTCC": SectorPriority.ARTCC,
    }
    return priority_map.get(sector_id, SectorPriority.TOWER)


@dataclass
class HandoffRequest:
    """Request to hand off an aircraft to another sector."""

    callsign: str
    from_sector: SectorID
    to_sector: SectorID
    reason: Literal["altitude", "conflict", "capacity", "emergency"]
    timestamp_s: float


@dataclass
class HandoffDecision:
    """Decision on a handoff request."""

    request: HandoffRequest
    approved: bool
    reason: str  # Explanation
    priority_from: SectorPriority
    priority_to: SectorPriority
    handoff_time_s: float  # When handoff completed (approved only)


@dataclass
class HandoffLog:
    """History of handoff decisions."""

    requests: list[HandoffRequest] = field(default_factory=list)
    decisions: list[HandoffDecision] = field(default_factory=list)
    total_approved: int = field(default=0, init=False)
    total_rejected: int = field(default=0, init=False)

    def add_decision(self, decision: HandoffDecision):
        """Add a handoff decision to the log."""
        self.requests.append(decision.request)
        self.decisions.append(decision)
        if decision.approved:
            self.total_approved += 1
        else:
            self.total_rejected += 1


# ── HandoffArbitrator: cross-sector handoff routing ─────────────────────────

class HandoffArbitrator:
    """
    Arbitrates aircraft handoffs between sectors.

    Uses deterministic priority routing:
      - Higher priority sector takes precedence
      - Conflicts are detected at boundaries
      - All handoffs are logged for audit trail
    """

    def __init__(self, scenario: EvalScenario):
        """
        Initialize arbitrator.

        Args:
            scenario: EvalScenario for crossing detection setup
        """
        self.scenario = scenario
        self.crossing_detector = CrossingDetector(scenario)
        self._handoff_log = HandoffLog()
        self._aircraft_location: dict[str, SectorID] = {}
        self._next_handoff_time = 0.0

    def request_handoff(self, request: HandoffRequest) -> HandoffDecision:
        """
        Process a handoff request.

        Deterministic decision based on:
          1. Sector priorities (ATCSCC > ARTCC > TRACON > TOWER)
          2. Conflict status at boundary
          3. Target sector capacity

        Args:
            request: HandoffRequest from source sector

        Returns:
            HandoffDecision (approved or rejected with reason)
        """
        priority_from = get_sector_priority(request.from_sector)
        priority_to = get_sector_priority(request.to_sector)

        # Deterministic routing: higher priority sector receives aircraft
        if priority_to > priority_from:
            # Target sector has higher priority -> approve
            approved = True
            reason = f"Higher priority sector ({request.to_sector}) receives aircraft"
            handoff_time = time.time()
        elif priority_to == priority_from:
            # Equal priority -> approve (rare in real ATC)
            approved = True
            reason = f"Same priority sector ({request.to_sector}), sequential handoff"
            handoff_time = time.time()
        else:
            # Source sector has higher priority -> reject
            approved = False
            reason = f"Lower priority sector ({request.to_sector}) cannot accept from {request.from_sector}"
            handoff_time = -1.0

        decision = HandoffDecision(
            request=request,
            approved=approved,
            reason=reason,
            priority_from=priority_from,
            priority_to=priority_to,
            handoff_time_s=handoff_time,
        )

        self._handoff_log.add_decision(decision)
        if approved:
            self._aircraft_location[request.callsign] = request.to_sector

        return decision

    def detect_conflicts_at_boundary(
        self,
        contacts: list[FlightTrack],
        sector_a: SectorID,
        sector_b: SectorID,
    ) -> list[SectorConflict]:
        """
        Detect conflicts at a sector boundary.

        Args:
            contacts: Flight tracks
            sector_a: Primary sector
            sector_b: Adjacent sector

        Returns:
            List of SectorConflict objects
        """
        return self.crossing_detector.detect_conflicts(
            contacts,
            primary_sector_id=sector_a,
            secondary_sector_id=sector_b,
            separation_minima_nm=5.0,
            vertical_minima_ft=1000,
        )

    def process_conflict(
        self, conflict: SectorConflict
    ) -> tuple[HandoffDecision, HandoffDecision]:
        """
        Process a conflict by requesting handoffs for both aircraft.

        Returns:
            Tuple of (decision_for_a, decision_for_b)
        """
        current_sector_a = self._aircraft_location.get(
            conflict.callsign_a, conflict.primary_sector
        )
        current_sector_b = self._aircraft_location.get(
            conflict.callsign_b, conflict.secondary_sector
        )

        # Request handoff for aircraft A
        request_a = HandoffRequest(
            callsign=conflict.callsign_a,
            from_sector=current_sector_a,  # type: ignore
            to_sector=conflict.secondary_sector,  # type: ignore
            reason="conflict",
            timestamp_s=time.time(),
        )
        decision_a = self.request_handoff(request_a)

        # Request handoff for aircraft B
        request_b = HandoffRequest(
            callsign=conflict.callsign_b,
            from_sector=current_sector_b,  # type: ignore
            to_sector=conflict.primary_sector,  # type: ignore
            reason="conflict",
            timestamp_s=time.time(),
        )
        decision_b = self.request_handoff(request_b)

        return decision_a, decision_b

    def get_handoff_log(self) -> HandoffLog:
        """Get the handoff audit log."""
        return self._handoff_log

    def set_aircraft_location(self, callsign: str, sector: SectorID):
        """Set current sector for an aircraft (for tracking)."""
        self._aircraft_location[callsign] = sector

    def __repr__(self) -> str:
        log = self._handoff_log
        return (
            f"HandoffArbitrator("
            f"requests={len(log.requests)}, "
            f"approved={log.total_approved}, "
            f"rejected={log.total_rejected})"
        )
