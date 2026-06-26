"""AeroSense eval harness (AeroOps M1) — evaluates the deterministic safety layer
against golden scenarios with a frozen pass-rate baseline. Ported and adapted from
the AutoRedTeam eval harness; binary metrics kept for the M1+ model-upgrade gate.
"""

from core.eval.harness import EvalReport, regression, run
from core.eval.metrics import BinaryMetrics, evaluate_binary, pass_rate

__all__ = ["EvalReport", "regression", "run", "BinaryMetrics", "evaluate_binary", "pass_rate"]
