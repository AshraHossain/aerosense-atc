"""
Federated Eval Coordinator for APEX ATC Platform (M6)

Baseline scenario harness that runs identical scenarios on all sectors and computes
aggregated pass-rate baselines. Used by EvalHarness in Phase 4.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TypedDict
from core.state import FlightTrack, Sector


# ── Type definitions ───────────────────────────────────────────────────────────

class ScenarioMetrics(TypedDict):
    """Metrics from a single scenario execution."""

    scenario_id: str
    sector_id: str
    pass_rate: float  # 0.0–1.0 (phase outcomes that matched expected)
    latency_ms: float  # Total execution time
    phases_completed: int  # How many of 12 phases executed
    error_count: int  # Phases that raised exceptions
    trace_hash: str  # SHA256 of decision trace (for determinism check)


class AggregatedMetrics(TypedDict):
    """Aggregated metrics across all sectors."""

    scenario_id: str
    min_pass_rate: float
    median_pass_rate: float
    max_pass_rate: float
    avg_latency_ms: float
    total_errors: int
    all_traces_identical: bool  # True if all sectors produced same trace


# ── EvalScenario: baseline test case ───────────────────────────────────────────

@dataclass(frozen=True)
class EvalScenario:
    """
    A baseline scenario for federated evaluation.

    Attributes:
        scenario_id: Unique identifier (e.g., "nominal_v1", "conflict_v2")
        name: Human-readable name
        description: What this scenario tests
        contacts: List of initial flight tracks
        sectors: Sector definitions for this scenario
        expected_outcomes: Dict of assertions (e.g., {"conflicts_detected": 1})
    """

    scenario_id: str
    name: str
    description: str
    contacts: list[FlightTrack]
    sectors: list[Sector]
    expected_outcomes: dict[str, int | float | str]

    @classmethod
    def nominal(cls) -> EvalScenario:
        """Baseline nominal scenario (no conflicts, 6 aircraft)."""
        return cls(
            scenario_id="nominal_v1",
            name="Nominal Operations",
            description="6 aircraft in normal ops, no conflicts, no emergencies",
            contacts=[
                {
                    "callsign": "AAL123",
                    "squawk": "1234",
                    "position": {"lat": 39.861389, "lon": -104.673056, "alt_ft": 35000},
                    "heading_deg": 90,
                    "speed_kts": 450,
                    "vertical_rate_fpm": 0,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
                {
                    "callsign": "DAL456",
                    "squawk": "2456",
                    "position": {"lat": 39.861389, "lon": -104.5, "alt_ft": 25000},
                    "heading_deg": 90,
                    "speed_kts": 400,
                    "vertical_rate_fpm": 0,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
                {
                    "callsign": "UAL789",
                    "squawk": "3789",
                    "position": {"lat": 40.1, "lon": -104.673056, "alt_ft": 15000},
                    "heading_deg": 270,
                    "speed_kts": 350,
                    "vertical_rate_fpm": 0,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
                {
                    "callsign": "SWA101",
                    "squawk": "4101",
                    "position": {"lat": 39.6, "lon": -104.7, "alt_ft": 8000},
                    "heading_deg": 180,
                    "speed_kts": 250,
                    "vertical_rate_fpm": 500,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
                {
                    "callsign": "FDX202",
                    "squawk": "5202",
                    "position": {"lat": 39.5, "lon": -104.6, "alt_ft": 5000},
                    "heading_deg": 0,
                    "speed_kts": 200,
                    "vertical_rate_fpm": 300,
                    "track_quality": 0.9,
                    "data_sources": ["radar_1"],
                },
                {
                    "callsign": "JBU303",
                    "squawk": "6303",
                    "position": {"lat": 39.8, "lon": -104.5, "alt_ft": 3000},
                    "heading_deg": 45,
                    "speed_kts": 150,
                    "vertical_rate_fpm": 200,
                    "track_quality": 0.8,
                    "data_sources": ["radar_1"],
                },
            ],
            sectors=[
                {
                    "sector_id": "HIGH",
                    "name": "High Altitude En-Route",
                    "alt_low_ft": 18000,
                    "alt_high_ft": 45000,
                    "traffic_count": 2,
                    "load_pct": 20.0,
                    "controller": "CTR-HIGH",
                },
                {
                    "sector_id": "EAST",
                    "name": "East Arrival",
                    "alt_low_ft": 10000,
                    "alt_high_ft": 18000,
                    "traffic_count": 1,
                    "load_pct": 8.0,
                    "controller": "CTR-EAST",
                },
                {
                    "sector_id": "APCH",
                    "name": "Approach Control",
                    "alt_low_ft": 0,
                    "alt_high_ft": 10000,
                    "traffic_count": 3,
                    "load_pct": 37.5,
                    "controller": "APP-CTL",
                },
            ],
            expected_outcomes={
                "conflicts_detected": 0,
                "emergencies_handled": 0,
                "clearances_issued": 0,
                "sector_overloads": 0,
            },
        )

    @classmethod
    def conflict(cls) -> EvalScenario:
        """Conflict scenario (2 aircraft on collision course)."""
        return cls(
            scenario_id="conflict_v1",
            name="Separation Conflict",
            description="2 aircraft converging, <5 NM separation, conflict detection required",
            contacts=[
                {
                    "callsign": "AAL100",
                    "squawk": "1000",
                    "position": {"lat": 39.861389, "lon": -104.673056, "alt_ft": 20000},
                    "heading_deg": 90,
                    "speed_kts": 400,
                    "vertical_rate_fpm": 0,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
                {
                    "callsign": "DAL200",
                    "squawk": "2000",
                    "position": {"lat": 39.861389, "lon": -104.5, "alt_ft": 20000},
                    "heading_deg": 270,
                    "speed_kts": 400,
                    "vertical_rate_fpm": 0,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
            ],
            sectors=[
                {
                    "sector_id": "EAST",
                    "name": "East Arrival",
                    "alt_low_ft": 10000,
                    "alt_high_ft": 45000,
                    "traffic_count": 2,
                    "load_pct": 20.0,
                    "controller": "CTR-EAST",
                },
            ],
            expected_outcomes={
                "conflicts_detected": 1,
                "clearances_issued": 2,  # At least one for each aircraft
            },
        )

    @classmethod
    def emergency(cls) -> EvalScenario:
        """Emergency scenario (aircraft squawking 7700)."""
        return cls(
            scenario_id="emergency_v1",
            name="Emergency Declaration",
            description="1 aircraft squawking 7700 (mayday), immediate priority handling",
            contacts=[
                {
                    "callsign": "AAL999",
                    "squawk": "7700",
                    "position": {"lat": 39.861389, "lon": -104.673056, "alt_ft": 25000},
                    "heading_deg": 180,
                    "speed_kts": 300,
                    "vertical_rate_fpm": -500,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
                {
                    "callsign": "DAL111",
                    "squawk": "1111",
                    "position": {"lat": 39.8, "lon": -104.673056, "alt_ft": 25000},
                    "heading_deg": 0,
                    "speed_kts": 400,
                    "vertical_rate_fpm": 0,
                    "track_quality": 1.0,
                    "data_sources": ["adsb"],
                },
            ],
            sectors=[
                {
                    "sector_id": "HIGH",
                    "name": "High Altitude En-Route",
                    "alt_low_ft": 18000,
                    "alt_high_ft": 45000,
                    "traffic_count": 2,
                    "load_pct": 30.0,
                    "controller": "CTR-HIGH",
                },
            ],
            expected_outcomes={
                "emergencies_detected": 1,
                "emergency_clearances_issued": 1,
            },
        )


# ── EvalCoordinator: run scenarios on mock sectors, aggregate results ─────────

class EvalCoordinator:
    """
    Orchestrates federated baseline evaluations.

    For M6, this is a mock orchestrator (no actual LLM calls). Real harness
    (Phase 4: EvalHarness) will wire this to actual sector runs.
    """

    def __init__(self):
        self._baseline_results: dict[str, AggregatedMetrics] = {}
        self._run_count = 0

    def run_scenario(
        self,
        scenario: EvalScenario,
        sector_ids: list[str] = ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"],
    ) -> AggregatedMetrics:
        """
        Execute a scenario on all sectors and aggregate results.

        For M6 (mock), this returns synthetic metrics.
        Phase 4 (EvalHarness) replaces this with actual sector execution.

        Args:
            scenario: EvalScenario to run
            sector_ids: Sectors to execute on (default: 3 Denver sectors)

        Returns:
            AggregatedMetrics with per-sector + aggregate results
        """
        self._run_count += 1
        metrics_per_sector: list[ScenarioMetrics] = []

        # Deterministic trace hash: depends only on scenario, not sector or run count
        import hashlib
        import json

        # Hash the scenario itself (contacts + expected outcomes) for determinism
        scenario_seed = json.dumps(
            {
                "scenario_id": scenario.scenario_id,
                "contact_count": len(scenario.contacts),
                "sector_count": len(scenario.sectors),
                "expected_outcomes": scenario.expected_outcomes,
            },
            sort_keys=True,
        ).encode()
        deterministic_trace_hash = hashlib.sha256(scenario_seed).hexdigest()

        for sector_id in sector_ids:
            metric: ScenarioMetrics = {
                "scenario_id": scenario.scenario_id,
                "sector_id": sector_id,
                "pass_rate": 1.0 if scenario.scenario_id == "nominal_v1" else 0.95,
                "latency_ms": 500.0 + (len(scenario.contacts) * 50),
                "phases_completed": 12,
                "error_count": 0,
                "trace_hash": deterministic_trace_hash,
            }
            metrics_per_sector.append(metric)

        # Aggregate: min, median, max pass rates
        pass_rates = [m["pass_rate"] for m in metrics_per_sector]
        pass_rates_sorted = sorted(pass_rates)
        median_idx = len(pass_rates_sorted) // 2
        median_pass_rate = (
            pass_rates_sorted[median_idx]
            if len(pass_rates_sorted) % 2 == 1
            else (pass_rates_sorted[median_idx - 1] + pass_rates_sorted[median_idx]) / 2
        )

        latencies = [m["latency_ms"] for m in metrics_per_sector]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        trace_hashes = [m["trace_hash"] for m in metrics_per_sector]
        all_traces_identical = len(set(trace_hashes)) == 1

        agg: AggregatedMetrics = {
            "scenario_id": scenario.scenario_id,
            "min_pass_rate": min(pass_rates),
            "median_pass_rate": median_pass_rate,
            "max_pass_rate": max(pass_rates),
            "avg_latency_ms": avg_latency,
            "total_errors": sum(m["error_count"] for m in metrics_per_sector),
            "all_traces_identical": all_traces_identical,
        }

        self._baseline_results[scenario.scenario_id] = agg
        return agg

    def get_baseline(self, scenario_id: str) -> AggregatedMetrics | None:
        """Retrieve a stored baseline result."""
        return self._baseline_results.get(scenario_id)

    def lock_baseline(self, scenario_id: str) -> str:
        """
        Lock a baseline result (used in CI/CD).

        Returns a hash representing the locked baseline (for drift detection).
        """
        metrics = self.get_baseline(scenario_id)
        if not metrics:
            raise ValueError(f"No baseline for scenario {scenario_id}")

        import hashlib
        import json

        baseline_json = json.dumps(
            {
                "scenario": scenario_id,
                "min_pass_rate": metrics["min_pass_rate"],
                "median_pass_rate": metrics["median_pass_rate"],
                "max_pass_rate": metrics["max_pass_rate"],
            },
            sort_keys=True,
        )
        return hashlib.sha256(baseline_json.encode()).hexdigest()

    def detect_drift(self, scenario_id: str, current_metrics: AggregatedMetrics) -> dict[str, bool]:
        """
        Detect regression vs. locked baseline.

        Returns dict of {metric_name: is_regression} for each metric.
        """
        baseline = self.get_baseline(scenario_id)
        if not baseline:
            return {}

        return {
            "pass_rate_regression": current_metrics["min_pass_rate"] < baseline["min_pass_rate"],
            "latency_regression": current_metrics["avg_latency_ms"] > baseline["avg_latency_ms"] * 1.1,
            "error_increase": current_metrics["total_errors"] > baseline["total_errors"],
        }

    def list_baselines(self) -> list[str]:
        """List all locked baseline scenario IDs."""
        return list(self._baseline_results.keys())

    def __repr__(self) -> str:
        return f"EvalCoordinator(scenarios={len(self._baseline_results)}, runs={self._run_count})"
