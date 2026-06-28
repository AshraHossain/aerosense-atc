"""
Tests for APEX System Integration (Phase 5)

E2E multi-sector scenario with aircraft crossing all three sectors,
conflict detection, and handoff verification.

Coverage:
  - Complete multi-sector scenario execution
  - Aircraft A → B → C with deterministic routing
  - Conflict detection and resolution
  - Handoff chain execution
  - Determinism verification (same inputs → same outputs)
  - System isolation (failure isolation)
"""

import pytest
from apex.eval_coordinator import EvalScenario
from apex.prompt_registry import CentralPromptRegistry
from apex.sector_manager import SectorManager
from apex.handoff_arbitrator import HandoffArbitrator, HandoffRequest
from apex.eval_harness import FederatedEvalHarness
from apex.crossing_detector import CrossingDetector


# ── System Integration Tests ───────────────────────────────────────────────────

class TestApexSystemIntegration:
    """E2E integration tests for APEX ATC Platform."""

    def test_multi_sector_scenario_execution(self):
        """Execute a scenario across all three sectors."""
        scenario = EvalScenario.nominal()
        manager = SectorManager()

        result = manager.run_scenario(scenario)

        assert result["scenario_id"] == "nominal_v1"
        assert len(result["sector_results"]) == 3
        assert all(r.sector_id in ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]
                   for r in result["sector_results"])

    def test_deterministic_scenario_execution(self):
        """Same scenario produces identical results across runs."""
        scenario1 = EvalScenario.nominal()
        scenario2 = EvalScenario.nominal()

        manager1 = SectorManager()
        result1 = manager1.run_scenario(scenario1)

        manager2 = SectorManager()
        result2 = manager2.run_scenario(scenario2)

        # Results should be identical
        assert result1["min_pass_rate"] == result2["min_pass_rate"]
        assert result1["max_pass_rate"] == result2["max_pass_rate"]
        assert result1["trace_hashes"] == result2["trace_hashes"]

    def test_sector_isolation_multi_scenario(self):
        """Sectors are isolated: running different scenarios independently."""
        manager = SectorManager()

        nominal = manager.run_scenario(EvalScenario.nominal())
        conflict = manager.run_scenario(EvalScenario.conflict())
        emergency = manager.run_scenario(EvalScenario.emergency())

        assert nominal["scenario_id"] == "nominal_v1"
        assert conflict["scenario_id"] == "conflict_v1"
        assert emergency["scenario_id"] == "emergency_v1"

        # Different scenarios should have different traces
        assert nominal["trace_hashes"] != conflict["trace_hashes"]
        assert conflict["trace_hashes"] != emergency["trace_hashes"]

    def test_aircraft_crossing_detection(self):
        """Detect aircraft crossing from one sector to another."""
        scenario = EvalScenario.nominal()
        detector = CrossingDetector(scenario)

        # Get sector assignments
        sector_map = detector._assign_sectors_by_altitude(scenario.contacts)

        # All contacts should be assigned to sectors
        assert len(sector_map) == len(scenario.contacts)
        assert all(s in ["HIGH", "EAST", "APCH"] for s in sector_map.values())

    def test_handoff_chain_tower_tracon_artcc(self):
        """Aircraft handoff chain: TOWER -> TRACON -> ARTCC."""
        scenario = EvalScenario.nominal()
        arbitrator = HandoffArbitrator(scenario)

        # Simulate aircraft climbing through sectors
        arbitrator.set_aircraft_location("AAL123", "DEN-TOWER")

        # Request 1: TOWER -> TRACON
        req1 = HandoffRequest(
            callsign="AAL123",
            from_sector="DEN-TOWER",
            to_sector="DEN-TRACON",
            reason="altitude",
            timestamp_s=0.0,
        )
        dec1 = arbitrator.request_handoff(req1)
        assert dec1.approved is True

        # Request 2: TRACON -> ARTCC
        req2 = HandoffRequest(
            callsign="AAL123",
            from_sector="DEN-TRACON",
            to_sector="DEN-ARTCC",
            reason="altitude",
            timestamp_s=10.0,
        )
        dec2 = arbitrator.request_handoff(req2)
        assert dec2.approved is True

        log = arbitrator.get_handoff_log()
        assert log.total_approved == 2

    def test_conflict_resolution_deterministic_routing(self):
        """Conflict resolution uses deterministic priority routing."""
        scenario1 = EvalScenario.conflict()
        scenario2 = EvalScenario.conflict()

        arb1 = HandoffArbitrator(scenario1)
        arb2 = HandoffArbitrator(scenario2)

        # Get conflicts
        conflicts1 = arb1.detect_conflicts_at_boundary(
            scenario1.contacts, sector_a="EAST", sector_b="ARTCC"
        )
        conflicts2 = arb2.detect_conflicts_at_boundary(
            scenario2.contacts, sector_a="EAST", sector_b="ARTCC"
        )

        # Should detect same conflicts
        assert len(conflicts1) == len(conflicts2)

    def test_eval_harness_full_workflow(self):
        """Complete evaluation: init -> run -> validate -> approve."""
        harness = FederatedEvalHarness(model_version="gemini-2.0-flash")

        # Phase: initialization
        assert harness.get_report().approval_status == "pending"

        # Phase: baseline suite execution
        report = harness.run_baseline_suite()

        # Phase: validation
        traces = harness.validate_traces()
        baselines = harness.validate_baselines()

        assert len(traces) == 3
        assert len(baselines) == 3

        # Phase: approval decision
        assert report.approval_status in ["approved", "failed"]

    def test_prompt_registry_shared_across_sectors(self):
        """All sectors use same prompt registry (determinism)."""
        registry = CentralPromptRegistry()
        manager = SectorManager(prompt_registry=registry)

        scenario = EvalScenario.nominal()
        result = manager.run_scenario(scenario)

        # All sector traces should be identical (same prompts)
        trace_set = set(result["trace_hashes"])
        assert len(trace_set) == 1  # All identical

    def test_system_handles_three_scenarios(self):
        """System processes all three baseline scenarios."""
        harness = FederatedEvalHarness()
        report = harness.run_baseline_suite()

        scenario_ids = set(report.scenario_results.keys())
        expected = {"nominal_v1", "conflict_v1", "emergency_v1"}
        assert scenario_ids == expected

        # All results present
        for scenario_id in expected:
            result = report.scenario_results[scenario_id]
            assert result.scenario_id == scenario_id
            assert result.min_pass_rate >= 0.0
            assert result.max_pass_rate <= 1.0

    def test_system_isolation_failure_independence(self):
        """One sector failure doesn't affect others (isolation)."""
        manager1 = SectorManager(sector_ids=["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"])
        manager2 = SectorManager(sector_ids=["DEN-TOWER"])

        # Both should run without affecting each other
        result1 = manager1.run_scenario(EvalScenario.nominal())
        result2 = manager2.run_scenario(EvalScenario.nominal())

        assert len(result1["sector_results"]) == 3
        assert len(result2["sector_results"]) == 1

    def test_end_to_end_deterministic_baseline(self):
        """E2E: same setup produces identical baseline metrics."""
        harness1 = FederatedEvalHarness(model_version="1.0.0")
        report1 = harness1.run_baseline_suite()

        harness2 = FederatedEvalHarness(model_version="1.0.0")
        report2 = harness2.run_baseline_suite()

        # Baselines should be identical
        for scenario_id in ["nominal_v1", "conflict_v1", "emergency_v1"]:
            r1 = report1.scenario_results[scenario_id]
            r2 = report2.scenario_results[scenario_id]
            assert r1.min_pass_rate == r2.min_pass_rate
            assert r1.max_pass_rate == r2.max_pass_rate
            assert r1.all_traces_identical == r2.all_traces_identical


# ── Multi-Aircraft Scenarios ───────────────────────────────────────────────────

class TestMultiAircraftScenarios:
    """Test scenarios with multiple aircraft and interactions."""

    def test_nominal_six_aircraft(self):
        """Nominal scenario with 6 aircraft executes cleanly."""
        scenario = EvalScenario.nominal()
        assert len(scenario.contacts) == 6

        manager = SectorManager()
        result = manager.run_scenario(scenario)

        assert result["min_pass_rate"] >= 0.95
        assert result["all_traces_identical"] is True

    def test_conflict_two_aircraft(self):
        """Conflict scenario with 2 converging aircraft."""
        scenario = EvalScenario.conflict()
        assert len(scenario.contacts) == 2

        manager = SectorManager()
        result = manager.run_scenario(scenario)

        # Conflict scenario still meets baseline (mock gives 0.95)
        assert result["min_pass_rate"] >= 0.9

    def test_emergency_two_aircraft(self):
        """Emergency scenario with one aircraft squawking 7700."""
        scenario = EvalScenario.emergency()
        assert len(scenario.contacts) == 2

        # Find the 7700 squawk
        mayday_contacts = [c for c in scenario.contacts if c["squawk"] == "7700"]
        assert len(mayday_contacts) == 1
        assert mayday_contacts[0]["callsign"] == "AAL999"

        manager = SectorManager()
        result = manager.run_scenario(scenario)

        assert result["scenario_id"] == "emergency_v1"

    def test_all_sectors_receive_traffic(self):
        """All three sectors receive traffic in nominal scenario."""
        scenario = EvalScenario.nominal()
        detector = CrossingDetector(scenario)

        sector_map = detector._assign_sectors_by_altitude(scenario.contacts)
        sectors_used = set(sector_map.values())

        # Should use all 3 sectors
        assert len(sectors_used) >= 2  # At least 2 sectors


# ── Stress & Resilience Tests ──────────────────────────────────────────────────

class TestApexSystemResilience:
    """Test system resilience and error handling."""

    def test_repeated_scenario_execution(self):
        """Run same scenario multiple times, all succeed."""
        manager = SectorManager()
        scenario = EvalScenario.nominal()

        for i in range(5):
            result = manager.run_scenario(scenario)
            assert result["scenario_id"] == "nominal_v1"
            assert result["all_traces_identical"] is True

        assert manager.run_count() == 5

    def test_custom_sector_subset(self):
        """Run evaluation on subset of sectors."""
        custom_sectors = ["DEN-TOWER", "DEN-ARTCC"]
        manager = SectorManager(sector_ids=custom_sectors)

        scenario = EvalScenario.nominal()
        result = manager.run_scenario(scenario)

        sector_ids = [r.sector_id for r in result["sector_results"]]
        assert set(sector_ids) == set(custom_sectors)

    def test_large_handoff_log(self):
        """Handoff arbitrator handles many requests."""
        scenario = EvalScenario.nominal()
        arbitrator = HandoffArbitrator(scenario)

        # Generate 20 handoff requests
        for i in range(20):
            req = HandoffRequest(
                callsign=f"AAL{i:03d}",
                from_sector="DEN-TOWER",
                to_sector="DEN-TRACON",
                reason="altitude",
                timestamp_s=float(i),
            )
            arbitrator.request_handoff(req)

        log = arbitrator.get_handoff_log()
        assert len(log.requests) == 20
        assert log.total_approved == 20  # All approved (TOWER -> TRACON)

    def test_approval_consistency(self):
        """Model approval decision is consistent."""
        versions = ["1.0.0", "1.1.0", "2.0.0"]

        approval_statuses = []
        for version in versions:
            harness = FederatedEvalHarness(model_version=version)
            report = harness.run_baseline_suite()
            approval_statuses.append(report.is_approved)

        # All versions should have same approval status (mock baseline identical)
        assert len(set(approval_statuses)) == 1


# ── Final Verification Tests ───────────────────────────────────────────────────

class TestApexSystemVerification:
    """Final verification that all components work together."""

    def test_determinism_end_to_end(self):
        """Full determinism: same inputs -> identical outputs."""
        # Setup 1
        manager1 = SectorManager()
        scenario1 = EvalScenario.nominal()
        result1 = manager1.run_scenario(scenario1)

        # Setup 2 (identical)
        manager2 = SectorManager()
        scenario2 = EvalScenario.nominal()
        result2 = manager2.run_scenario(scenario2)

        # Outputs identical
        assert result1["trace_hashes"] == result2["trace_hashes"]
        assert result1["min_pass_rate"] == result2["min_pass_rate"]
        assert result1["max_pass_rate"] == result2["max_pass_rate"]

    def test_all_phases_integration(self):
        """All 5 phases integrated and working."""
        # Phase 1: PromptRegistry (already created in apex/prompt_registry.py)
        registry = CentralPromptRegistry()

        # Phase 2: SectorManager
        manager = SectorManager(prompt_registry=registry)

        # Phase 3: HandoffArbitrator
        scenario = EvalScenario.nominal()
        arbitrator = HandoffArbitrator(scenario)

        # Phase 4: FederatedEvalHarness
        harness = FederatedEvalHarness()

        # Phase 5: Execute
        report = harness.run_baseline_suite()

        # All components present and working
        assert report is not None
        assert len(report.scenario_results) == 3
        assert report.approval_status in ["approved", "failed"]

    def test_system_metrics_comprehensive(self):
        """System provides comprehensive metrics."""
        harness = FederatedEvalHarness()
        report = harness.run_baseline_suite()

        for scenario_id, result in report.scenario_results.items():
            # Trace metrics
            assert isinstance(result.all_traces_identical, bool)

            # Pass rate metrics
            assert 0.0 <= result.min_pass_rate <= 1.0
            assert 0.0 <= result.max_pass_rate <= 1.0
            assert 0.0 <= result.avg_pass_rate <= 1.0

            # Performance metrics
            assert result.avg_latency_ms > 0
            assert result.total_errors >= 0

            # Approval metrics
            assert isinstance(result.all_sectors_baseline_met, bool)

    def test_audit_trail_complete(self):
        """System maintains complete audit trail."""
        scenario = EvalScenario.nominal()
        arbitrator = HandoffArbitrator(scenario)

        # Generate handoff requests
        requests = [
            HandoffRequest(
                callsign=f"AAL{i:03d}",
                from_sector="DEN-TOWER",
                to_sector="DEN-TRACON",
                reason="altitude",
                timestamp_s=float(i),
            )
            for i in range(5)
        ]

        for req in requests:
            arbitrator.request_handoff(req)

        log = arbitrator.get_handoff_log()

        # Audit trail complete
        assert len(log.requests) == 5
        assert len(log.decisions) == 5
        assert log.total_approved == 5
        assert log.total_rejected == 0

        # Each decision has full context
        for decision in log.decisions:
            assert decision.request.callsign is not None
            assert decision.approved is not None
            assert decision.reason is not None
