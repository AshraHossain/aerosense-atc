"""Harness tests — report structure, pass-rate, category breakdown, regression
gate, and that an erroring check counts as a failure (never a crash)."""

import json
from pathlib import Path

from core.eval.golden import EvalCheck
from core.eval.harness import CheckResult, EvalReport, regression, run

BASELINE = json.loads((Path(__file__).parents[2] / "core" / "eval" / "baseline.json").read_text())


def test_run_returns_report():
    report = run()
    assert isinstance(report, EvalReport)
    assert len(report.results) >= 10


def test_all_golden_checks_pass():
    assert run().pass_rate == 1.0


def test_no_failures_on_clean_run():
    assert run().failures == []


def test_by_category_keys():
    cats = run().by_category()
    assert set(cats) == {"routing", "structure"}
    assert all(0.0 <= v <= 1.0 for v in cats.values())


def test_to_dict_shape():
    d = run().to_dict()
    assert set(d) >= {"pass_rate", "total", "passed", "by_category", "failures"}
    assert d["passed"] == d["total"]


def test_erroring_check_counts_as_failure_not_crash():
    def boom() -> bool:
        raise RuntimeError("kaboom")
    bad = EvalCheck("boom", "routing", boom, "raises on purpose")
    report = run([bad])
    assert report.pass_rate == 0.0
    assert report.failures[0].name == "boom"


def test_mixed_checks_pass_rate():
    checks = [
        EvalCheck("ok", "routing", lambda: True, ""),
        EvalCheck("nope", "routing", lambda: False, ""),
    ]
    assert run(checks).pass_rate == 0.5


def test_checkresult_records_description():
    checks = [EvalCheck("c", "structure", lambda: True, "desc here")]
    r = run(checks).results[0]
    assert isinstance(r, CheckResult)
    assert r.description == "desc here"


def test_regression_none_when_at_baseline():
    assert regression(run(), BASELINE["pass_rate"]) is None


def test_regression_none_when_improved():
    assert regression(run(), 0.5) is None


def test_regression_detected_when_below_baseline():
    report = run([EvalCheck("f", "routing", lambda: False, "")])  # pass_rate 0
    msg = regression(report, 1.0)
    assert msg is not None and "regressed" in msg


def test_baseline_is_one():
    # The deterministic safety layer must clear every golden check.
    assert BASELINE["pass_rate"] == 1.0
