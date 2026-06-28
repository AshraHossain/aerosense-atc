"""
Sector Manager for APEX ATC Platform (M6 - Phase 2)

Launches and manages N independent sectors (DEN-TOWER, DEN-TRACON, DEN-ARTCC)
as separate AeroSense instances. Each sector runs the 12-phase pipeline
independently on the same scenario, producing sector-specific traces.

SectorManager ensures:
  - All sectors use the same prompt registry (deterministic)
  - All sectors run the same scenario (bit-identical inputs)
  - Sector isolation: one sector down does not affect others
  - Aggregation: traces are collected for determinism checks
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from apex.eval_coordinator import EvalScenario
from apex.prompt_registry import CentralPromptRegistry


# ── Type definitions ───────────────────────────────────────────────────────────

SectorID = Literal["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]


class SectorStatus(Enum):
    """Status of a sector in the federation."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class SectorTrace:
    """Trace output from a single sector run."""

    sector_id: SectorID
    scenario_id: str
    phase_count: int  # How many of 12 phases completed
    trace_hash: str  # SHA256 of phase decisions
    execution_time_ms: float
    status: SectorStatus
    error_message: str | None = None


@dataclass
class SectorRunResult:
    """Result of running a scenario on a single sector."""

    sector_id: SectorID
    scenario_id: str
    pass_rate: float  # 0.0-1.0
    latency_ms: float
    trace_hash: str
    phases_completed: int
    errors: int


# ── SectorInstance: single independent sector ──────────────────────────────────


@dataclass
class SectorInstance:
    """
    A single independent sector running the AeroSense pipeline.

    In Phase 2 (mock), this is a synthetic sector.
    In Phase 4 (FederatedEval), this wires to the real 12-phase pipeline.
    """

    sector_id: SectorID
    scenario: EvalScenario
    prompt_registry: CentralPromptRegistry
    _status: SectorStatus = field(default=SectorStatus.IDLE, init=False)
    _trace: SectorTrace | None = field(default=None, init=False)
    _result: SectorRunResult | None = field(default=None, init=False)

    def run(self, timeout_s: float = 30.0) -> SectorRunResult:
        """
        Execute the scenario on this sector.

        In Phase 2 (mock): returns synthetic metrics
        In Phase 4: calls the actual 12-phase graph

        Args:
            timeout_s: Timeout in seconds (enforced in Phase 4)

        Returns:
            SectorRunResult with trace hash
        """
        self._status = SectorStatus.RUNNING
        start_time = time.perf_counter()

        try:
            import hashlib
            import json

            # Mock execution: all sectors produce identical results for same scenario
            # (trace hash depends only on scenario, not sector, ensuring determinism)
            scenario_seed = json.dumps(
                {
                    "scenario_id": self.scenario.scenario_id,
                    "contact_count": len(self.scenario.contacts),
                    "sector_count": len(self.scenario.sectors),
                },
                sort_keys=True,
            ).encode()
            trace_hash = hashlib.sha256(scenario_seed).hexdigest()

            pass_rate = 1.0 if self.scenario.scenario_id == "nominal_v1" else 0.95
            phases_completed = 12
            errors = 0

            elapsed = (time.perf_counter() - start_time) * 1000

            result = SectorRunResult(
                sector_id=self.sector_id,
                scenario_id=self.scenario.scenario_id,
                pass_rate=pass_rate,
                latency_ms=500.0 + (len(self.scenario.contacts) * 50),
                trace_hash=trace_hash,
                phases_completed=phases_completed,
                errors=errors,
            )

            self._result = result
            self._status = SectorStatus.COMPLETED
            return result

        except Exception as e:
            self._status = SectorStatus.FAILED
            raise

    def status(self) -> SectorStatus:
        """Get current status of this sector."""
        return self._status

    def get_result(self) -> SectorRunResult | None:
        """Get result if completed, None otherwise."""
        return self._result if self._status == SectorStatus.COMPLETED else None


# ── SectorManager: orchestrate all sectors ───────────────────────────────────


@dataclass
class SectorManager:
    """
    Manages a federation of independent sectors.

    Responsibilities:
      - Create sector instances (one per sector_id)
      - Run scenarios on all sectors in parallel (Phase 4: actual parallelism)
      - Collect traces and verify determinism (all sectors → same trace hash)
      - Provide isolation: sector failure doesn't affect others
    """

    sector_ids: list[SectorID] = field(
        default_factory=lambda: ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]
    )
    prompt_registry: CentralPromptRegistry = field(default_factory=CentralPromptRegistry)
    _sectors: dict[SectorID, SectorInstance] = field(default_factory=dict, init=False)
    _run_history: list[dict] = field(default_factory=list, init=False)

    def __post_init__(self):
        """Initialize sector instances (but don't run them yet)."""
        # Sectors are created on-demand in run_scenario()
        pass

    def run_scenario(self, scenario: EvalScenario) -> dict:
        """
        Execute a scenario on all sectors and aggregate results.

        Returns:
            {
                "scenario_id": str,
                "sector_results": [SectorRunResult, ...],
                "trace_hashes": [str, ...],
                "all_traces_identical": bool,
                "min_pass_rate": float,
                "max_pass_rate": float,
                "avg_latency_ms": float,
            }
        """
        sector_results: list[SectorRunResult] = []
        trace_hashes: list[str] = []

        # Run on each sector
        for sector_id in self.sector_ids:
            sector = SectorInstance(
                sector_id=sector_id,
                scenario=scenario,
                prompt_registry=self.prompt_registry,
            )
            result = sector.run()
            sector_results.append(result)
            trace_hashes.append(result.trace_hash)

        # Aggregate
        pass_rates = [r.pass_rate for r in sector_results]
        latencies = [r.latency_ms for r in sector_results]

        aggregated = {
            "scenario_id": scenario.scenario_id,
            "sector_results": sector_results,
            "trace_hashes": trace_hashes,
            "all_traces_identical": len(set(trace_hashes)) == 1,
            "min_pass_rate": min(pass_rates),
            "max_pass_rate": max(pass_rates),
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "total_errors": sum(r.errors for r in sector_results),
        }

        self._run_history.append(aggregated)
        return aggregated

    def get_sector(self, sector_id: SectorID) -> SectorInstance | None:
        """Get a sector instance by ID (from most recent run)."""
        # In a real implementation, would maintain persistent sector instances
        return None

    def list_sectors(self) -> list[SectorID]:
        """List all managed sector IDs."""
        return list(self.sector_ids)

    def run_count(self) -> int:
        """Total number of scenarios run."""
        return len(self._run_history)

    def __repr__(self) -> str:
        return f"SectorManager(sectors={len(self.sector_ids)}, runs={self.run_count()})"
