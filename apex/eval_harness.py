"""
Federated Eval Harness for APEX ATC Platform (M6 - Phase 4)

Executes evaluation scenarios across federated sectors and verifies that
all sectors meet minimum baseline performance (≥95%) before model approval.

Responsibilities:
  - Run all three baseline scenarios (nominal, conflict, emergency)
  - Collect traces from all sectors
  - Verify determinism (all sectors → identical traces)
  - Compute baseline metrics (pass rates, latency, errors)
  - Validate all sectors ≥95% baseline
  - Report drift detection and approval status
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from apex.eval_coordinator import EvalScenario
from apex.prompt_registry import CentralPromptRegistry
from apex.sector_manager import SectorManager


# ── Type definitions ───────────────────────────────────────────────────────────

EvalStatus = Literal["pending", "running", "completed", "failed", "approved"]


@dataclass
class EvalResult:
    """Result of evaluating all sectors on one scenario."""

    scenario_id: str
    min_pass_rate: float
    max_pass_rate: float
    avg_pass_rate: float
    all_sectors_baseline_met: bool  # min_pass_rate >= 0.95
    all_traces_identical: bool
    total_errors: int
    avg_latency_ms: float


@dataclass
class EvalReport:
    """Complete evaluation report for model approval."""

    model_version: str
    scenario_results: dict[str, EvalResult] = field(default_factory=dict)
    approval_status: EvalStatus = "pending"
    approval_reason: str = ""
    timestamp_s: float = 0.0

    @property
    def is_approved(self) -> bool:
        """Model is approved if all scenarios meet baselines."""
        if not self.scenario_results:
            return False
        return all(r.all_sectors_baseline_met for r in self.scenario_results.values())

    def get_failure_summary(self) -> str:
        """Get summary of failed scenarios."""
        failures = [
            f"{s_id}: {r.min_pass_rate:.1%}"
            for s_id, r in self.scenario_results.items()
            if not r.all_sectors_baseline_met
        ]
        return ", ".join(failures) if failures else "none"


# ── FederatedEvalHarness: evaluation orchestrator ────────────────────────────

class FederatedEvalHarness:
    """
    Orchestrates federated evaluation across all sectors.

    Ensures:
      - All sectors use same prompts (deterministic)
      - All sectors run same scenarios (identical inputs)
      - All sectors meet ≥95% baseline before approval
      - Determinism verified (traces identical across sectors)
    """

    def __init__(self, model_version: str = "1.0.0"):
        """
        Initialize eval harness.

        Args:
            model_version: Model version string for tracking (e.g., "gemini-2.0-flash")
        """
        self.model_version = model_version
        self.sector_manager = SectorManager()
        self.prompt_registry = CentralPromptRegistry()
        self._report = EvalReport(model_version=model_version)

    def run_baseline_suite(self) -> EvalReport:
        """
        Run all three baseline scenarios on all sectors.

        Returns:
            EvalReport with pass-rate results and approval status
        """
        import time

        self._report.timestamp_s = time.time()
        self._report.approval_status = "running"

        scenarios = [
            ("nominal_v1", EvalScenario.nominal()),
            ("conflict_v1", EvalScenario.conflict()),
            ("emergency_v1", EvalScenario.emergency()),
        ]

        for scenario_id, scenario in scenarios:
            result = self._eval_scenario(scenario)
            self._report.scenario_results[scenario_id] = result

        # Determine approval status
        if self._report.is_approved:
            self._report.approval_status = "approved"
            self._report.approval_reason = "All scenarios meet ≥95% baseline"
        else:
            self._report.approval_status = "failed"
            self._report.approval_reason = f"Failed baselines: {self._report.get_failure_summary()}"

        return self._report

    def _eval_scenario(self, scenario: EvalScenario) -> EvalResult:
        """
        Evaluate a single scenario across all sectors.

        Args:
            scenario: EvalScenario to run

        Returns:
            EvalResult with aggregated metrics
        """
        manager_result = self.sector_manager.run_scenario(scenario)

        pass_rates = [r.pass_rate for r in manager_result["sector_results"]]
        min_pr = min(pass_rates) if pass_rates else 0.0
        max_pr = max(pass_rates) if pass_rates else 0.0
        avg_pr = sum(pass_rates) / len(pass_rates) if pass_rates else 0.0

        result = EvalResult(
            scenario_id=scenario.scenario_id,
            min_pass_rate=min_pr,
            max_pass_rate=max_pr,
            avg_pass_rate=avg_pr,
            all_sectors_baseline_met=min_pr >= 0.95,
            all_traces_identical=manager_result["all_traces_identical"],
            total_errors=manager_result["total_errors"],
            avg_latency_ms=manager_result["avg_latency_ms"],
        )

        return result

    def get_report(self) -> EvalReport:
        """Get the evaluation report."""
        return self._report

    def validate_traces(self) -> dict[str, bool]:
        """
        Validate that traces are identical across sectors for each scenario.

        Returns:
            {scenario_id: all_identical}
        """
        return {
            s_id: r.all_traces_identical for s_id, r in self._report.scenario_results.items()
        }

    def validate_baselines(self) -> dict[str, float]:
        """
        Validate baseline metrics for each scenario.

        Returns:
            {scenario_id: min_pass_rate}
        """
        return {s_id: r.min_pass_rate for s_id, r in self._report.scenario_results.items()}

    def __repr__(self) -> str:
        return (
            f"FederatedEvalHarness("
            f"model={self.model_version}, "
            f"scenarios={len(self._report.scenario_results)}, "
            f"status={self._report.approval_status})"
        )
