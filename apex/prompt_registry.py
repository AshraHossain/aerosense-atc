"""
Central Prompt Registry for APEX ATC Platform (M6)

All sectors use the same versioned prompts. A model upgrade bumps the version once;
all sectors auto-sync on next scenario run. Registry is read-only after init.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, TypedDict
from core.prompts import PromptTemplate as _PromptTemplate


# ── Type definitions ───────────────────────────────────────────────────────────

SectorID = Literal["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]
PhaseID = Literal[
    "phase_01_surveillance",
    "phase_02_flight_plan",
    "phase_03_sector",
    "phase_04_conflict",
    "phase_05_clearance",
    "phase_06_communications",
    "phase_07_handoff",
    "phase_08_weather",
    "phase_09_emergency",
    "phase_10_tfm",
    "phase_11_audit",
    "phase_12_supervisor",
]


# ── PromptVersion: immutable versioned prompt ──────────────────────────────────

@dataclass(frozen=True)
class PromptVersion:
    """
    Immutable versioned prompt snapshot.

    Attributes:
        name: Phase name (e.g., "phase_01_surveillance")
        version: Semantic version (e.g., "1.0.0")
        text: Full prompt text
        sha256_hash: SHA256 of prompt text (for integrity verification)
        metadata: Dict of annotations (author, date, change_notes, etc.)
    """

    name: str
    version: str
    text: str
    sha256_hash: str
    metadata: dict[str, str]

    def __post_init__(self):
        """Verify hash matches text."""
        expected_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.sha256_hash != expected_hash:
            raise ValueError(
                f"PromptVersion {self.name}@{self.version}: "
                f"hash mismatch (declared {self.sha256_hash}, got {expected_hash})"
            )

    @classmethod
    def from_template(
        cls,
        template: _PromptTemplate,
        metadata: dict[str, str] | None = None,
    ) -> PromptVersion:
        """Create PromptVersion from a core/prompts.py PromptTemplate."""
        return cls(
            name=template.name,
            version=template.version,
            text=template.template,
            sha256_hash=template.sha256,
            metadata=metadata or {},
        )


# ── CentralPromptRegistry: read-only, per-sector + per-phase ───────────────────

class CentralPromptRegistry:
    """
    Central registry of versioned prompts for all sectors.

    Structure:
        registry[sector_id][phase_id] = PromptVersion

    Properties:
      - Read-only after initialization (frozen)
      - All sectors pin same version for each phase (no per-sector overrides)
      - Version changes trigger sector cache invalidation (handled by SectorManager)
      - Hash verification on init (fail fast if integrity lost)
    """

    def __init__(
        self,
        prompts: dict[SectorID, dict[PhaseID, PromptVersion]] | None = None,
    ):
        """
        Initialize registry.

        Args:
            prompts: Nested dict {sector_id: {phase_id: PromptVersion}}.
                     If None, creates empty registry (for testing).
        """
        self._registry: dict[SectorID, dict[PhaseID, PromptVersion]] = prompts or {}
        self._frozen = False

    def get(
        self,
        sector_id: SectorID,
        phase_id: PhaseID,
    ) -> PromptVersion:
        """
        Retrieve a prompt version.

        Args:
            sector_id: Target sector (DEN-TOWER, DEN-TRACON, DEN-ARTCC)
            phase_id: Phase (phase_01_surveillance, etc.)

        Returns:
            PromptVersion

        Raises:
            KeyError: if sector_id or phase_id not found
        """
        if sector_id not in self._registry:
            raise KeyError(f"Sector {sector_id} not in registry")
        if phase_id not in self._registry[sector_id]:
            raise KeyError(f"Phase {phase_id} not in registry for sector {sector_id}")
        return self._registry[sector_id][phase_id]

    def get_all_phases(self, sector_id: SectorID) -> dict[PhaseID, PromptVersion]:
        """Get all phase prompts for a sector."""
        if sector_id not in self._registry:
            raise KeyError(f"Sector {sector_id} not in registry")
        return dict(self._registry[sector_id])

    def list_sectors(self) -> list[SectorID]:
        """List all registered sectors."""
        return list(self._registry.keys())

    def list_phases(self, sector_id: SectorID) -> list[PhaseID]:
        """List all phase IDs for a sector."""
        if sector_id not in self._registry:
            raise KeyError(f"Sector {sector_id} not in registry")
        return list(self._registry[sector_id].keys())

    def version_for_phase(self, sector_id: SectorID, phase_id: PhaseID) -> str:
        """Get version string for a phase."""
        prompt = self.get(sector_id, phase_id)
        return prompt.version

    def hash_for_phase(self, sector_id: SectorID, phase_id: PhaseID) -> str:
        """Get SHA256 hash for a phase prompt."""
        prompt = self.get(sector_id, phase_id)
        return prompt.sha256_hash

    def freeze(self) -> None:
        """Freeze registry (prevent further mutations). Called after final setup."""
        self._frozen = True

    def is_frozen(self) -> bool:
        """Check if registry is frozen (read-only)."""
        return self._frozen

    def __repr__(self) -> str:
        sectors = self.list_sectors()
        return (
            f"CentralPromptRegistry("
            f"sectors={sectors}, "
            f"frozen={self._frozen})"
        )


# ── Factory: build default registry with 3 sectors ────────────────────────────

def build_default_registry(
    sector_ids: list[SectorID] = ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"],
) -> CentralPromptRegistry:
    """
    Build default registry with 3 sectors, all phases pinned to same version.

    For M6, all sectors use identical prompts (no per-sector customization).
    Future: allow per-sector overrides via environment variables.

    Args:
        sector_ids: List of sector IDs to register (default: 3 Denver sectors)

    Returns:
        CentralPromptRegistry (unfrozen, ready for init or testing)
    """
    # Import here to avoid circular imports
    from core import prompts as core_prompts

    prompts: dict[SectorID, dict[PhaseID, PromptVersion]] = {}

    for sector_id in sector_ids:
        # All sectors get same phase prompts (reuse core.prompts registry)
        sector_phases: dict[PhaseID, PromptVersion] = {}
        for template in core_prompts.all_prompts():
            # Map core phase names to M6 PhaseID type
            # core.prompts uses "phase_NN.system" naming
            phase_id = template.name.replace(".system", "")
            sector_phases[phase_id] = PromptVersion.from_template(
                template,
                metadata={
                    "sector": sector_id,
                    "locked_at": "2026-06-26",
                },
            )
        prompts[sector_id] = sector_phases

    return CentralPromptRegistry(prompts)


def build_test_registry(
    prompts: dict[SectorID, dict[PhaseID, PromptVersion]] | None = None,
    frozen: bool = False,
) -> CentralPromptRegistry:
    """
    Build a test registry (empty or with given prompts).

    Args:
        prompts: Optional nested dict of prompts (for fixture setup)
        frozen: If True, freeze the registry immediately

    Returns:
        CentralPromptRegistry
    """
    registry = CentralPromptRegistry(prompts)
    if frozen:
        registry.freeze()
    return registry
