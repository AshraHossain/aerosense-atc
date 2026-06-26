"""Eval harness — runs the golden safety checks and reports a pass-rate, with a
frozen-baseline regression gate (ported from AutoRedTeam's eval pattern).

The harness runs the *real* core.routing functions (via the checks in golden.py),
so a regression in the safety layer shows up as a dropped pass-rate here and fails
the gate, instead of shipping silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.eval.golden import CHECKS, EvalCheck
from core.eval.metrics import pass_rate


@dataclass(frozen=True)
class CheckResult:
    name: str
    category: str
    passed: bool
    description: str


@dataclass(frozen=True)
class EvalReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return pass_rate([r.passed for r in self.results])

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    def by_category(self) -> dict[str, float]:
        cats: dict[str, list[bool]] = {}
        for r in self.results:
            cats.setdefault(r.category, []).append(r.passed)
        return {c: pass_rate(v) for c, v in cats.items()}

    def to_dict(self) -> dict:
        return {
            "pass_rate": self.pass_rate,
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "by_category": self.by_category(),
            "failures": [r.name for r in self.failures],
        }


def _run_check(check: EvalCheck) -> CheckResult:
    try:
        passed = bool(check.predicate())
    except Exception:
        passed = False  # a check that errors is a failed check, never a crash
    return CheckResult(check.name, check.category, passed, check.description)


def run(checks: list[EvalCheck] | None = None) -> EvalReport:
    return EvalReport([_run_check(c) for c in (checks if checks is not None else CHECKS)])


def regression(report: EvalReport, baseline_pass_rate: float, *, tol: float = 1e-9) -> str | None:
    """Return a message if the pass-rate fell below baseline, else None."""
    if report.pass_rate < baseline_pass_rate - tol:
        return (f"pass_rate regressed: {report.pass_rate:.4f} < "
                f"baseline {baseline_pass_rate:.4f}")
    return None
