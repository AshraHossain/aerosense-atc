"""
Tests for APEX FederatedEvalHarness (Phase 4)

Coverage:
  - Running baseline suite (nominal, conflict, emergency)
  - Baseline validation (all sectors ≥95%)
  - Trace determinism verification
  - Model approval workflow
  - Drift detection reporting
"""

import pytest
from apex.eval_harness import FederatedEvalHarness, EvalResult, EvalReport


# ── EvalResult Tests ───────────────────────────────────────────────────────────

class TestEvalResult:
    """EvalResult validation."""

    def test_eval_result_creation(self):
        """Create an EvalResult."""
        result = EvalResult(
            scenario_id="nominal_v1",
            min_pass_rate=1.0,
            max_pass_rate=1.0,
            avg_pass_rate=1.0,
            all_sectors_baseline_met=True,
            all_traces_identical=True,
            total_errors=0,
            avg_latency_ms=750.0,
        )

        assert result.scenario_id == "nominal_v1"
        assert result.all_sectors_baseline_met is True

    def test_eval_result_baseline_met(self):
        """Baseline met when min_pass_rate >= 0.95."""
        result = EvalResult(
            scenario_id="conflict_v1",
            min_pass_rate=0.95,
            max_pass_rate=0.99,
            avg_pass_rate=0.97,
            all_sectors_baseline_met=True,
            all_traces_identical=True,
            total_errors=0,
            avg_latency_ms=800.0,
        )

        assert result.all_sectors_baseline_met is True

    def test_eval_result_baseline_not_met(self):
        """Baseline not met when min_pass_rate < 0.95."""
        result = EvalResult(
            scenario_id="conflict_v1",
            min_pass_rate=0.85,
            max_pass_rate=0.95,
            avg_pass_rate=0.90,
            all_sectors_baseline_met=False,
            all_traces_identical=True,
            total_errors=1,
            avg_latency_ms=800.0,
        )

        assert result.all_sectors_baseline_met is False


# ── EvalReport Tests ───────────────────────────────────────────────────────────

class TestEvalReport:
    """EvalReport approval and status tracking."""

    def test_eval_report_creation(self):
        """Create an EvalReport."""
        report = EvalReport(model_version="1.0.0")

        assert report.model_version == "1.0.0"
        assert report.approval_status == "pending"
        assert len(report.scenario_results) == 0

    def test_eval_report_approval_empty(self):
        """Empty report is not approved."""
        report = EvalReport(model_version="1.0.0")

        assert report.is_approved is False

    def test_eval_report_approval_all_scenarios_pass(self):
        """Report approved when all scenarios meet baselines."""
        report = EvalReport(model_version="1.0.0")

        report.scenario_results["nominal_v1"] = EvalResult(
            scenario_id="nominal_v1",
            min_pass_rate=1.0,
            max_pass_rate=1.0,
            avg_pass_rate=1.0,
            all_sectors_baseline_met=True,
            all_traces_identical=True,
            total_errors=0,
            avg_latency_ms=750.0,
        )
        report.scenario_results["conflict_v1"] = EvalResult(
            scenario_id="conflict_v1",
            min_pass_rate=0.95,
            max_pass_rate=0.99,
            avg_pass_rate=0.97,
            all_sectors_baseline_met=True,
            all_traces_identical=True,
            total_errors=0,
            avg_latency_ms=800.0,
        )

        assert report.is_approved is True

    def test_eval_report_approval_one_scenario_fails(self):
        """Report not approved if one scenario fails."""
        report = EvalReport(model_version="1.0.0")

        report.scenario_results["nominal_v1"] = EvalResult(
            scenario_id="nominal_v1",
            min_pass_rate=1.0,
            max_pass_rate=1.0,
            avg_pass_rate=1.0,
            all_sectors_baseline_met=True,
            all_traces_identical=True,
            total_errors=0,
            avg_latency_ms=750.0,
        )
        report.scenario_results["conflict_v1"] = EvalResult(
            scenario_id="conflict_v1",
            min_pass_rate=0.85,
            max_pass_rate=0.95,
            avg_pass_rate=0.90,
            all_sectors_baseline_met=False,
            all_traces_identical=True,
            total_errors=1,
            avg_latency_ms=800.0,
        )

        assert report.is_approved is False

    def test_eval_report_failure_summary(self):
        """Get summary of failed scenarios."""
        report = EvalReport(model_version="1.0.0")

        report.scenario_results["conflict_v1"] = EvalResult(
            scenario_id="conflict_v1",
            min_pass_rate=0.85,
            max_pass_rate=0.95,
            avg_pass_rate=0.90,
            all_sectors_baseline_met=False,
            all_traces_identical=True,
            total_errors=1,
            avg_latency_ms=800.0,
        )

        summary = report.get_failure_summary()
        assert "conflict_v1" in summary
        assert "85" in summary


# ── FederatedEvalHarness Tests ─────────────────────────────────────────────────

class TestFederatedEvalHarness:
    """FederatedEvalHarness orchestration."""

    def test_harness_creation(self):
        """Create a FederatedEvalHarness."""
        harness = FederatedEvalHarness(model_version="gemini-2.0-flash")

        assert harness.model_version == "gemini-2.0-flash"
        assert harness.get_report().approval_status == "pending"

    def test_run_baseline_suite(self):
        """Run baseline suite on all scenarios."""
        harness = FederatedEvalHarness()

        report = harness.run_baseline_suite()

        assert len(report.scenario_results) == 3
        assert "nominal_v1" in report.scenario_results
        assert "conflict_v1" in report.scenario_results
        assert "emergency_v1" in report.scenario_results

    def test_baseline_suite_approval_nominal(self):
        """Baseline suite runs and nominal scenario passes."""
        harness = FederatedEvalHarness()

        report = harness.run_baseline_suite()

        nominal_result = report.scenario_results.get("nominal_v1")
        assert nominal_result is not None
        assert nominal_result.all_sectors_baseline_met is True

    def test_baseline_suite_status_running_to_approved(self):
        """Approval status transitions: pending -> running -> approved."""
        harness = FederatedEvalHarness()

        assert harness.get_report().approval_status == "pending"
        report = harness.run_baseline_suite()
        assert report.approval_status in ["approved", "failed"]

    def test_harness_validates_traces(self):
        """Validate traces are identical across sectors."""
        harness = FederatedEvalHarness()
        harness.run_baseline_suite()

        traces = harness.validate_traces()

        assert "nominal_v1" in traces
        assert isinstance(traces["nominal_v1"], bool)

    def test_harness_validates_baselines(self):
        """Validate baseline pass rates."""
        harness = FederatedEvalHarness()
        harness.run_baseline_suite()

        baselines = harness.validate_baselines()

        assert "nominal_v1" in baselines
        assert 0.0 <= baselines["nominal_v1"] <= 1.0

    def test_harness_reports_all_metrics(self):
        """Harness reports complete metrics for each scenario."""
        harness = FederatedEvalHarness()
        harness.run_baseline_suite()

        report = harness.get_report()

        for scenario_id, result in report.scenario_results.items():
            assert result.scenario_id == scenario_id
            assert 0.0 <= result.min_pass_rate <= 1.0
            assert 0.0 <= result.max_pass_rate <= 1.0
            assert 0.0 <= result.avg_pass_rate <= 1.0
            # Allow small floating-point error
            assert result.min_pass_rate <= result.avg_pass_rate + 1e-6
            assert result.avg_pass_rate <= result.max_pass_rate + 1e-6
            assert result.avg_latency_ms > 0
            assert isinstance(result.all_traces_identical, bool)
            assert result.total_errors >= 0

    def test_harness_repr(self):
        """FederatedEvalHarness has readable repr."""
        harness = FederatedEvalHarness(model_version="test-1.0")
        harness.run_baseline_suite()

        repr_str = repr(harness)
        assert "FederatedEvalHarness" in repr_str
        assert "test-1.0" in repr_str
        assert "scenarios=3" in repr_str


# ── Determinism Tests ──────────────────────────────────────────────────────────

class TestEvalHarnessDeterminism:
    """Verify deterministic evaluation results."""

    def test_same_model_same_results(self):
        """Running same model twice produces same baseline metrics."""
        harness1 = FederatedEvalHarness(model_version="1.0.0")
        report1 = harness1.run_baseline_suite()

        harness2 = FederatedEvalHarness(model_version="1.0.0")
        report2 = harness2.run_baseline_suite()

        # Pass rates should be identical
        for scenario_id in ["nominal_v1", "conflict_v1", "emergency_v1"]:
            result1 = report1.scenario_results[scenario_id]
            result2 = report2.scenario_results[scenario_id]
            assert result1.min_pass_rate == result2.min_pass_rate
            assert result1.max_pass_rate == result2.max_pass_rate

    def test_traces_identical_across_sectors(self):
        """All sectors produce identical traces for same scenario."""
        harness = FederatedEvalHarness()
        report = harness.run_baseline_suite()

        # For nominal scenario, traces should be identical across all sectors
        nominal_result = report.scenario_results["nominal_v1"]
        assert nominal_result.all_traces_identical is True

    def test_approval_decision_deterministic(self):
        """Approval decision is deterministic (same model -> same decision)."""
        harness1 = FederatedEvalHarness(model_version="1.0.0")
        report1 = harness1.run_baseline_suite()

        harness2 = FederatedEvalHarness(model_version="1.0.0")
        report2 = harness2.run_baseline_suite()

        assert report1.is_approved == report2.is_approved
        assert report1.approval_status == report2.approval_status


# ── Integration Tests ──────────────────────────────────────────────────────────

class TestEvalHarnessIntegration:
    """Integration tests for complete eval workflow."""

    def test_complete_evaluation_workflow(self):
        """Complete workflow: init -> run -> validate -> approve."""
        harness = FederatedEvalHarness(model_version="gemini-2.0-flash")

        # Initial state
        assert harness.get_report().approval_status == "pending"

        # Run baseline suite
        report = harness.run_baseline_suite()
        assert report.approval_status in ["approved", "failed"]

        # Validate metrics
        baselines = harness.validate_baselines()
        assert len(baselines) == 3

        traces = harness.validate_traces()
        assert len(traces) == 3

    def test_nominal_scenario_meets_baseline(self):
        """Nominal scenario meets 95% baseline (mock gives 100%)."""
        harness = FederatedEvalHarness()
        report = harness.run_baseline_suite()

        nominal = report.scenario_results["nominal_v1"]
        assert nominal.all_sectors_baseline_met is True
        assert nominal.min_pass_rate >= 0.95

    def test_all_scenarios_processed(self):
        """All three baseline scenarios are processed."""
        harness = FederatedEvalHarness()
        report = harness.run_baseline_suite()

        scenario_ids = set(report.scenario_results.keys())
        expected = {"nominal_v1", "conflict_v1", "emergency_v1"}
        assert scenario_ids == expected

    def test_approval_summary_on_failure(self):
        """Approval summary shows failed scenarios."""
        harness = FederatedEvalHarness()
        report = harness.run_baseline_suite()

        if not report.is_approved:
            summary = report.get_failure_summary()
            assert summary != "none"
        else:
            # All passed
            summary = report.get_failure_summary()
            assert summary == "none"

    def test_harness_integration_with_sector_manager(self):
        """Harness successfully integrates with SectorManager."""
        harness = FederatedEvalHarness()

        # Sector manager should be accessible
        assert harness.sector_manager is not None

        # Should have 3 sectors
        assert len(harness.sector_manager.list_sectors()) == 3

        # Run suite should work without error
        report = harness.run_baseline_suite()
        assert report is not None
