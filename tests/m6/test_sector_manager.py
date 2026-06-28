"""
Tests for APEX SectorManager (Phase 2)

Coverage:
  - SectorInstance creation and execution
  - SectorManager orchestration of independent sectors
  - Determinism: all sectors produce identical traces for same scenario
  - Isolation: sector failure doesn't affect others
  - Aggregation of sector results
"""

import pytest
from apex.eval_coordinator import EvalScenario
from apex.prompt_registry import CentralPromptRegistry
from apex.sector_manager import (
    SectorInstance,
    SectorManager,
    SectorStatus,
    SectorRunResult,
)


# ── SectorInstance Tests ───────────────────────────────────────────────────────

class TestSectorInstance:
    """SectorInstance creation and execution."""

    def test_sector_instance_creation(self):
        """Create a sector instance."""
        scenario = EvalScenario.nominal()
        registry = CentralPromptRegistry()
        sector = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario,
            prompt_registry=registry,
        )

        assert sector.sector_id == "DEN-TOWER"
        assert sector.status() == SectorStatus.IDLE
        assert sector.get_result() is None

    def test_sector_run_nominal(self):
        """Run nominal scenario on a sector."""
        scenario = EvalScenario.nominal()
        registry = CentralPromptRegistry()
        sector = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario,
            prompt_registry=registry,
        )

        result = sector.run()

        assert isinstance(result, SectorRunResult)
        assert result.sector_id == "DEN-TOWER"
        assert result.scenario_id == "nominal_v1"
        assert 0.0 <= result.pass_rate <= 1.0
        assert result.latency_ms > 0
        assert result.phases_completed == 12
        assert result.errors == 0
        assert len(result.trace_hash) == 64  # SHA256 hex

    def test_sector_run_conflict(self):
        """Run conflict scenario on a sector."""
        scenario = EvalScenario.conflict()
        registry = CentralPromptRegistry()
        sector = SectorInstance(
            sector_id="DEN-TRACON",
            scenario=scenario,
            prompt_registry=registry,
        )

        result = sector.run()

        assert result.sector_id == "DEN-TRACON"
        assert result.scenario_id == "conflict_v1"
        assert result.pass_rate >= 0.9  # Mock gives 0.95

    def test_sector_run_updates_status(self):
        """Running a sector updates its status."""
        scenario = EvalScenario.nominal()
        registry = CentralPromptRegistry()
        sector = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario,
            prompt_registry=registry,
        )

        assert sector.status() == SectorStatus.IDLE
        sector.run()
        assert sector.status() == SectorStatus.COMPLETED

    def test_sector_get_result_after_run(self):
        """Get result after sector run."""
        scenario = EvalScenario.nominal()
        registry = CentralPromptRegistry()
        sector = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario,
            prompt_registry=registry,
        )

        result1 = sector.run()
        result2 = sector.get_result()

        assert result1 == result2

    def test_sector_trace_hash_deterministic(self):
        """Same scenario always produces same trace hash."""
        scenario1 = EvalScenario.nominal()
        scenario2 = EvalScenario.nominal()
        registry = CentralPromptRegistry()

        sector1 = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario1,
            prompt_registry=registry,
        )
        result1 = sector1.run()

        sector2 = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario2,
            prompt_registry=registry,
        )
        result2 = sector2.run()

        assert result1.trace_hash == result2.trace_hash

    def test_sector_all_three_ids(self):
        """All three sector IDs work."""
        scenario = EvalScenario.nominal()
        registry = CentralPromptRegistry()

        for sector_id in ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]:
            sector = SectorInstance(
                sector_id=sector_id,
                scenario=scenario,
                prompt_registry=registry,
            )
            result = sector.run()
            assert result.sector_id == sector_id

    def test_sector_latency_scales_with_contacts(self):
        """Latency should scale with contact count."""
        scenario_nominal = EvalScenario.nominal()  # 6 contacts
        scenario_conflict = EvalScenario.conflict()  # 2 contacts
        registry = CentralPromptRegistry()

        sector1 = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario_nominal,
            prompt_registry=registry,
        )
        result1 = sector1.run()

        sector2 = SectorInstance(
            sector_id="DEN-TOWER",
            scenario=scenario_conflict,
            prompt_registry=registry,
        )
        result2 = sector2.run()

        # Nominal has more contacts, should have higher latency
        assert result1.latency_ms > result2.latency_ms


# ── SectorManager Tests ────────────────────────────────────────────────────────

class TestSectorManager:
    """SectorManager orchestration of multiple sectors."""

    def test_manager_creation(self):
        """Create SectorManager."""
        manager = SectorManager()

        assert manager is not None
        assert len(manager.list_sectors()) == 3
        assert "DEN-TOWER" in manager.list_sectors()
        assert "DEN-TRACON" in manager.list_sectors()
        assert "DEN-ARTCC" in manager.list_sectors()

    def test_manager_custom_sectors(self):
        """Create manager with custom sector list."""
        sectors = ["DEN-TOWER", "DEN-TRACON"]
        manager = SectorManager(sector_ids=sectors)

        assert len(manager.list_sectors()) == 2
        assert manager.list_sectors() == sectors

    def test_manager_run_nominal_scenario(self):
        """Run nominal scenario on all sectors."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        assert result["scenario_id"] == "nominal_v1"
        assert len(result["sector_results"]) == 3
        assert len(result["trace_hashes"]) == 3
        assert result["min_pass_rate"] >= 0.9
        assert result["max_pass_rate"] <= 1.0

    def test_manager_all_traces_identical_nominal(self):
        """Nominal scenario: all sectors produce identical traces."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        # All hashes should be identical (same scenario input)
        assert result["all_traces_identical"] is True
        assert len(set(result["trace_hashes"])) == 1

    def test_manager_run_conflict_scenario(self):
        """Run conflict scenario on all sectors."""
        manager = SectorManager()
        scenario = EvalScenario.conflict()

        result = manager.run_scenario(scenario)

        assert result["scenario_id"] == "conflict_v1"
        assert result["min_pass_rate"] >= 0.9

    def test_manager_run_emergency_scenario(self):
        """Run emergency scenario on all sectors."""
        manager = SectorManager()
        scenario = EvalScenario.emergency()

        result = manager.run_scenario(scenario)

        assert result["scenario_id"] == "emergency_v1"

    def test_manager_aggregation_min_max(self):
        """Manager aggregates min/max correctly."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        pass_rates = [r.pass_rate for r in result["sector_results"]]
        assert result["min_pass_rate"] == min(pass_rates)
        assert result["max_pass_rate"] == max(pass_rates)

    def test_manager_aggregation_avg_latency(self):
        """Manager computes average latency."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        latencies = [r.latency_ms for r in result["sector_results"]]
        expected_avg = sum(latencies) / len(latencies)
        assert result["avg_latency_ms"] == expected_avg

    def test_manager_total_errors_aggregation(self):
        """Manager aggregates error counts."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        total_errors = sum(r.errors for r in result["sector_results"])
        assert result["total_errors"] == total_errors

    def test_manager_run_count(self):
        """Manager tracks run count."""
        manager = SectorManager()

        assert manager.run_count() == 0

        manager.run_scenario(EvalScenario.nominal())
        assert manager.run_count() == 1

        manager.run_scenario(EvalScenario.conflict())
        assert manager.run_count() == 2

    def test_manager_multiple_runs_identical_traces(self):
        """Multiple runs of same scenario produce identical traces."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result1 = manager.run_scenario(scenario)
        result2 = manager.run_scenario(EvalScenario.nominal())

        # Traces should be identical across runs
        assert result1["trace_hashes"] == result2["trace_hashes"]

    def test_manager_repr(self):
        """SectorManager has readable repr."""
        manager = SectorManager()
        manager.run_scenario(EvalScenario.nominal())

        repr_str = repr(manager)
        assert "SectorManager" in repr_str
        assert "sectors=3" in repr_str
        assert "runs=1" in repr_str


# ── Determinism Tests ──────────────────────────────────────────────────────────

class TestSectorDeterminism:
    """Verify deterministic sector execution."""

    def test_same_scenario_same_trace_across_runs(self):
        """Running same scenario twice gives same trace hashes."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result1 = manager.run_scenario(scenario)
        result2 = manager.run_scenario(EvalScenario.nominal())

        assert result1["trace_hashes"] == result2["trace_hashes"]

    def test_different_scenarios_different_traces(self):
        """Different scenarios produce different traces."""
        manager = SectorManager()
        scenario1 = EvalScenario.nominal()
        scenario2 = EvalScenario.conflict()

        result1 = manager.run_scenario(scenario1)
        result2 = manager.run_scenario(scenario2)

        assert result1["trace_hashes"] != result2["trace_hashes"]

    def test_all_sectors_trace_identical_nominal(self):
        """For nominal scenario, all sectors produce byte-for-byte identical traces."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        # All trace hashes should be identical
        trace_set = set(result["trace_hashes"])
        assert len(trace_set) == 1, f"Expected 1 unique trace, got {len(trace_set)}"

    def test_sector_isolation_pass_rate(self):
        """All sectors report same pass rate for same scenario."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        pass_rates = [r.pass_rate for r in result["sector_results"]]
        # All should be same for nominal
        assert len(set(pass_rates)) == 1


# ── Integration Tests ──────────────────────────────────────────────────────────

class TestSectorIntegration:
    """Integration tests for sector orchestration."""

    def test_manager_all_three_scenarios(self):
        """Run all three baseline scenarios on all sectors."""
        manager = SectorManager()

        nominal = manager.run_scenario(EvalScenario.nominal())
        conflict = manager.run_scenario(EvalScenario.conflict())
        emergency = manager.run_scenario(EvalScenario.emergency())

        assert nominal["scenario_id"] == "nominal_v1"
        assert conflict["scenario_id"] == "conflict_v1"
        assert emergency["scenario_id"] == "emergency_v1"

        assert manager.run_count() == 3

    def test_sector_results_structure(self):
        """Sector results have all required fields."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        for sector_result in result["sector_results"]:
            assert isinstance(sector_result, SectorRunResult)
            assert sector_result.sector_id in ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]
            assert sector_result.scenario_id == "nominal_v1"
            assert 0.0 <= sector_result.pass_rate <= 1.0
            assert sector_result.latency_ms > 0
            assert sector_result.phases_completed == 12
            assert sector_result.errors >= 0
            assert len(sector_result.trace_hash) == 64

    def test_custom_sector_ids_work(self):
        """Custom sector ID list works end-to-end."""
        custom_sectors = ["DEN-TOWER", "DEN-ARTCC"]
        manager = SectorManager(sector_ids=custom_sectors)
        scenario = EvalScenario.nominal()

        result = manager.run_scenario(scenario)

        sector_ids = [r.sector_id for r in result["sector_results"]]
        assert set(sector_ids) == set(custom_sectors)

    def test_manager_isolation_scenario_independence(self):
        """Scenarios are independent (result of one doesn't affect another)."""
        manager = SectorManager()

        result1 = manager.run_scenario(EvalScenario.nominal())
        result2 = manager.run_scenario(EvalScenario.conflict())
        result3 = manager.run_scenario(EvalScenario.nominal())

        # Result 1 and 3 should be identical (same scenario)
        assert result1["trace_hashes"] == result3["trace_hashes"]

        # Result 2 should be different (different scenario)
        assert result1["trace_hashes"] != result2["trace_hashes"]
