"""
Tests for APEX EvalCoordinator (Phase 1)

Coverage:
  - EvalScenario creation (nominal, conflict, emergency)
  - EvalCoordinator scenario execution
  - Metrics aggregation (min/median/max pass rates, latency)
  - Baseline locking and drift detection
  - Determinism (2 runs → identical output)
"""

import pytest
from apex.eval_coordinator import EvalCoordinator, EvalScenario


# ── EvalScenario Tests ─────────────────────────────────────────────────────────

class TestEvalScenario:
    """EvalScenario creation and validation."""

    def test_nominal_scenario_creation(self):
        """Create nominal scenario."""
        scenario = EvalScenario.nominal()

        assert scenario.scenario_id == "nominal_v1"
        assert scenario.name == "Nominal Operations"
        assert len(scenario.contacts) == 6
        assert len(scenario.sectors) == 3
        assert scenario.expected_outcomes["conflicts_detected"] == 0
        assert scenario.expected_outcomes["emergencies_handled"] == 0

    def test_conflict_scenario_creation(self):
        """Create conflict scenario."""
        scenario = EvalScenario.conflict()

        assert scenario.scenario_id == "conflict_v1"
        assert scenario.name == "Separation Conflict"
        assert len(scenario.contacts) == 2
        assert scenario.expected_outcomes["conflicts_detected"] == 1
        assert scenario.expected_outcomes["clearances_issued"] == 2

    def test_emergency_scenario_creation(self):
        """Create emergency scenario."""
        scenario = EvalScenario.emergency()

        assert scenario.scenario_id == "emergency_v1"
        assert scenario.name == "Emergency Declaration"
        assert len(scenario.contacts) == 2
        assert scenario.expected_outcomes["emergencies_detected"] == 1

    def test_nominal_contacts_structure(self):
        """Nominal scenario contacts have required fields."""
        scenario = EvalScenario.nominal()

        for contact in scenario.contacts:
            assert "callsign" in contact
            assert "squawk" in contact
            assert "position" in contact
            assert "heading_deg" in contact
            assert "speed_kts" in contact
            assert "vertical_rate_fpm" in contact
            assert "track_quality" in contact
            assert "data_sources" in contact

    def test_nominal_sectors_structure(self):
        """Nominal scenario sectors have required fields."""
        scenario = EvalScenario.nominal()

        for sector in scenario.sectors:
            assert "sector_id" in sector
            assert "name" in sector
            assert "alt_low_ft" in sector
            assert "alt_high_ft" in sector
            assert "traffic_count" in sector
            assert "load_pct" in sector
            assert "controller" in sector

    def test_scenario_immutability(self):
        """EvalScenario is frozen (immutable)."""
        scenario = EvalScenario.nominal()

        with pytest.raises((AttributeError, TypeError)):
            scenario.scenario_id = "modified_v1"


# ── EvalCoordinator Tests ──────────────────────────────────────────────────────

class TestEvalCoordinator:
    """EvalCoordinator scenario execution and aggregation."""

    def test_coordinator_creation(self):
        """Create EvalCoordinator."""
        coordinator = EvalCoordinator()
        assert coordinator is not None
        assert len(coordinator.list_baselines()) == 0

    def test_run_nominal_scenario(self):
        """Run nominal scenario and get aggregated metrics."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        metrics = coordinator.run_scenario(scenario)

        assert metrics["scenario_id"] == "nominal_v1"
        assert 0.0 <= metrics["min_pass_rate"] <= 1.0
        assert 0.0 <= metrics["median_pass_rate"] <= 1.0
        assert 0.0 <= metrics["max_pass_rate"] <= 1.0
        assert metrics["min_pass_rate"] <= metrics["median_pass_rate"] <= metrics["max_pass_rate"]
        assert metrics["avg_latency_ms"] > 0
        assert metrics["total_errors"] >= 0
        assert isinstance(metrics["all_traces_identical"], bool)

    def test_run_conflict_scenario(self):
        """Run conflict scenario."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.conflict()

        metrics = coordinator.run_scenario(scenario)

        assert metrics["scenario_id"] == "conflict_v1"
        assert metrics["min_pass_rate"] >= 0.9  # Mock gives 0.95

    def test_run_emergency_scenario(self):
        """Run emergency scenario."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.emergency()

        metrics = coordinator.run_scenario(scenario)

        assert metrics["scenario_id"] == "emergency_v1"

    def test_run_scenario_three_sectors(self):
        """Run scenario on all 3 default sectors."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        metrics = coordinator.run_scenario(
            scenario, sector_ids=["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]
        )

        # All three sectors should participate
        assert metrics["min_pass_rate"] >= 0.0
        assert metrics["max_pass_rate"] <= 1.0

    def test_coordinator_stores_baseline(self):
        """Coordinator stores results after run."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        coordinator.run_scenario(scenario)

        baseline = coordinator.get_baseline("nominal_v1")
        assert baseline is not None
        assert baseline["scenario_id"] == "nominal_v1"

    def test_get_baseline_nonexistent(self):
        """Getting a non-existent baseline returns None."""
        coordinator = EvalCoordinator()

        baseline = coordinator.get_baseline("nonexistent_scenario")
        assert baseline is None

    def test_list_baselines(self):
        """List all stored baselines."""
        coordinator = EvalCoordinator()

        coordinator.run_scenario(EvalScenario.nominal())
        coordinator.run_scenario(EvalScenario.conflict())

        baselines = coordinator.list_baselines()
        assert len(baselines) == 2
        assert "nominal_v1" in baselines
        assert "conflict_v1" in baselines

    def test_lock_baseline(self):
        """Lock a baseline (returns hash for drift detection)."""
        coordinator = EvalCoordinator()
        coordinator.run_scenario(EvalScenario.nominal())

        hash_val = coordinator.lock_baseline("nominal_v1")

        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA256 hex length

    def test_lock_baseline_nonexistent(self):
        """Locking a non-existent baseline raises ValueError."""
        coordinator = EvalCoordinator()

        with pytest.raises(ValueError):
            coordinator.lock_baseline("nonexistent_scenario")

    def test_detect_drift_same_metrics(self):
        """Drift detection with identical metrics shows no regression."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        metrics1 = coordinator.run_scenario(scenario)

        # Same metrics, no drift
        drift = coordinator.detect_drift("nominal_v1", metrics1)

        assert not drift.get("pass_rate_regression", False)
        assert not drift.get("error_increase", False)

    def test_detect_drift_regression(self):
        """Drift detection catches pass rate regression."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        coordinator.run_scenario(scenario)
        baseline = coordinator.get_baseline("nominal_v1")

        # Artificially create worse metrics
        worse_metrics = dict(baseline)
        worse_metrics["min_pass_rate"] = baseline["min_pass_rate"] * 0.8

        drift = coordinator.detect_drift("nominal_v1", worse_metrics)

        assert drift.get("pass_rate_regression", False)

    def test_latency_included_in_metrics(self):
        """Scenario metrics include latency in milliseconds."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        metrics = coordinator.run_scenario(scenario)

        # Latency should scale with contact count (~500 base + 50 per contact)
        expected_min_latency = 500 + (len(scenario.contacts) * 50)
        assert metrics["avg_latency_ms"] >= expected_min_latency


# ── Determinism Tests ──────────────────────────────────────────────────────────

class TestEvalDeterminism:
    """Verify deterministic scenario execution."""

    def test_scenario_run_determinism(self):
        """Multiple runs of same scenario with fresh coordinator produce same pass rates."""
        scenario = EvalScenario.nominal()

        coordinator1 = EvalCoordinator()
        metrics1 = coordinator1.run_scenario(scenario)

        coordinator2 = EvalCoordinator()
        metrics2 = coordinator2.run_scenario(scenario)

        # Pass rates should be identical (mock gives 1.0 for nominal)
        assert metrics1["min_pass_rate"] == metrics2["min_pass_rate"]
        assert metrics1["median_pass_rate"] == metrics2["median_pass_rate"]
        assert metrics1["max_pass_rate"] == metrics2["max_pass_rate"]

    def test_traces_identical_across_sectors(self):
        """Nominal scenario: all sectors produce identical trace hashes."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        metrics = coordinator.run_scenario(scenario)

        # For nominal, mock should report all traces identical
        assert metrics["all_traces_identical"] is True

    def test_same_scenario_run_twice_gives_same_aggregates(self):
        """Run same scenario twice, aggregates are identical."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        metrics1 = coordinator.run_scenario(scenario)
        # Note: coordinator tracks run count, but semantics don't change
        # In real harness, this would test full determinism

        scenario2 = EvalScenario.nominal()
        metrics2 = coordinator.run_scenario(scenario2)

        # Pass rates should match
        assert metrics1["min_pass_rate"] == metrics2["min_pass_rate"]


# ── Integration Tests ──────────────────────────────────────────────────────────

class TestEvalIntegration:
    """Integration tests combining multiple operations."""

    def test_all_three_scenarios(self):
        """Run all three baseline scenarios."""
        coordinator = EvalCoordinator()

        nominal = coordinator.run_scenario(EvalScenario.nominal())
        conflict = coordinator.run_scenario(EvalScenario.conflict())
        emergency = coordinator.run_scenario(EvalScenario.emergency())

        assert nominal["scenario_id"] == "nominal_v1"
        assert conflict["scenario_id"] == "conflict_v1"
        assert emergency["scenario_id"] == "emergency_v1"

        baselines = coordinator.list_baselines()
        assert len(baselines) == 3

    def test_baseline_locking_workflow(self):
        """Realistic workflow: run scenario, lock baseline, detect drift."""
        coordinator = EvalCoordinator()
        scenario = EvalScenario.nominal()

        # Run baseline
        metrics = coordinator.run_scenario(scenario)
        baseline_hash = coordinator.lock_baseline("nominal_v1")

        # Simulate regression
        worse_metrics = dict(metrics)
        worse_metrics["total_errors"] = 5

        drift = coordinator.detect_drift("nominal_v1", worse_metrics)
        assert drift.get("error_increase", False)

    def test_coordinator_repr(self):
        """EvalCoordinator has readable repr."""
        coordinator = EvalCoordinator()
        coordinator.run_scenario(EvalScenario.nominal())

        repr_str = repr(coordinator)
        assert "EvalCoordinator" in repr_str
        assert "scenarios=1" in repr_str
        assert "runs=1" in repr_str
