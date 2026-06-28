"""
Aircraft Crossing Detector for APEX ATC Platform (M6 - Phase 3)

Detects when an aircraft transitions between sectors and potential conflicts
at sector boundaries. Used by HandoffArbitrator to route handoff requests.

Detection logic:
  - Track aircraft movement across sector altitude ranges
  - Identify boundary crossings (entry/exit)
  - Flag conflicts at sector seams (separation minima violated)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from apex.eval_coordinator import EvalScenario
from core.state import FlightTrack


# ── Type definitions ───────────────────────────────────────────────────────────

@dataclass
class SectorBoundary:
    """Definition of a sector's airspace boundary."""

    sector_id: str
    alt_low_ft: int
    alt_high_ft: int
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


@dataclass
class Crossing:
    """Detection of an aircraft crossing a sector boundary."""

    callsign: str
    from_sector_id: str | None  # None if entering airspace
    to_sector_id: str | None  # None if exiting airspace
    crossing_type: Literal["entry", "exit", "transfer"]  # transfer = sector to sector
    altitude_ft: int
    confidence: float  # 0.0-1.0


@dataclass
class SectorConflict:
    """Detection of a conflict at a sector boundary."""

    callsign_a: str
    callsign_b: str
    primary_sector: str  # Where conflict detected
    secondary_sector: str  # Adjacent sector
    separation_nm: float  # Current separation in nautical miles
    minimum_separation_nm: float  # FAA minimum
    time_to_conflict_s: float  # Estimated seconds until CFLICT


# ── Helper: great-circle distance ──────────────────────────────────────────────

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance in nautical miles.

    Args:
        lat1, lon1, lat2, lon2: Latitude/longitude in decimal degrees

    Returns:
        Distance in nautical miles
    """
    R_nm = 3440.065  # Earth's radius in nautical miles

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return R_nm * c


# ── CrossingDetector: identify sector transitions ────────────────────────────

class CrossingDetector:
    """
    Detects aircraft crossing sector boundaries.

    In Phase 3 (mock): identifies crossings from scenario definition
    In Phase 4+: integrates with real track updates
    """

    def __init__(self, scenario: EvalScenario):
        """
        Initialize detector with sector boundaries from scenario.

        Args:
            scenario: EvalScenario with sector definitions
        """
        self.scenario = scenario
        self._boundaries: dict[str, SectorBoundary] = {}
        self._build_boundaries()

    def _build_boundaries(self):
        """Build sector boundary definitions from scenario sectors."""
        # For mock, use sector altitude ranges + a default geographic area
        denver_lat_min, denver_lat_max = 39.5, 40.2
        denver_lon_min, denver_lon_max = -105.0, -104.5

        for sector in self.scenario.sectors:
            boundary = SectorBoundary(
                sector_id=sector["sector_id"],
                alt_low_ft=sector["alt_low_ft"],
                alt_high_ft=sector["alt_high_ft"],
                lat_min=denver_lat_min,
                lat_max=denver_lat_max,
                lon_min=denver_lon_min,
                lon_max=denver_lon_max,
            )
            self._boundaries[sector["sector_id"]] = boundary

    def detect_crossings(
        self, contacts: list[FlightTrack], current_sector_map: dict[str, str] | None = None
    ) -> list[Crossing]:
        """
        Detect sector crossings for given contacts.

        Args:
            contacts: List of flight tracks
            current_sector_map: Dict {callsign: current_sector_id}
                If None, assigns sectors by altitude

        Returns:
            List of Crossing objects
        """
        if current_sector_map is None:
            current_sector_map = self._assign_sectors_by_altitude(contacts)

        crossings: list[Crossing] = []
        # In a full implementation, would compare against previous track state
        # For Phase 3 mock, just return empty list (no state history)
        return crossings

    def _assign_sectors_by_altitude(self, contacts: list[FlightTrack]) -> dict[str, str]:
        """Assign each contact to a sector based on altitude."""
        sector_map: dict[str, str] = {}

        for contact in contacts:
            alt_ft = contact["position"]["alt_ft"]

            # Find sector by altitude range
            for sector_id, boundary in self._boundaries.items():
                if boundary.alt_low_ft <= alt_ft <= boundary.alt_high_ft:
                    sector_map[contact["callsign"]] = sector_id
                    break

        return sector_map

    def detect_conflicts(
        self,
        contacts: list[FlightTrack],
        primary_sector_id: str,
        secondary_sector_id: str | None = None,
        separation_minima_nm: float = 5.0,
        vertical_minima_ft: int = 1000,
    ) -> list[SectorConflict]:
        """
        Detect conflicts at sector boundary.

        Args:
            contacts: Flight tracks to check
            primary_sector_id: Sector where conflict detected
            secondary_sector_id: Adjacent sector (if applicable)
            separation_minima_nm: Minimum horizontal separation (NM)
            vertical_minima_ft: Minimum vertical separation (feet)

        Returns:
            List of detected SectorConflict objects
        """
        conflicts: list[SectorConflict] = []

        # For each pair of contacts, check separation
        for i, contact_a in enumerate(contacts):
            for contact_b in contacts[i + 1 :]:
                pos_a = contact_a["position"]
                pos_b = contact_b["position"]

                # Horizontal separation
                h_sep_nm = haversine_distance(
                    pos_a["lat"],
                    pos_a["lon"],
                    pos_b["lat"],
                    pos_b["lon"],
                )

                # Vertical separation
                v_sep_ft = abs(pos_a["alt_ft"] - pos_b["alt_ft"])

                # Check if conflict
                h_conflict = h_sep_nm < separation_minima_nm
                v_conflict = v_sep_ft < vertical_minima_ft

                if h_conflict and v_conflict:
                    conflicts.append(
                        SectorConflict(
                            callsign_a=contact_a["callsign"],
                            callsign_b=contact_b["callsign"],
                            primary_sector=primary_sector_id,
                            secondary_sector=secondary_sector_id or "UNKNOWN",
                            separation_nm=h_sep_nm,
                            minimum_separation_nm=separation_minima_nm,
                            time_to_conflict_s=0.0,  # Would need velocity for real calc
                        )
                    )

        return conflicts

    def get_sector_for_contact(self, contact: FlightTrack) -> str | None:
        """Determine which sector a contact belongs to (by altitude)."""
        alt_ft = contact["position"]["alt_ft"]

        for sector_id, boundary in self._boundaries.items():
            if boundary.alt_low_ft <= alt_ft <= boundary.alt_high_ft:
                return sector_id

        return None
