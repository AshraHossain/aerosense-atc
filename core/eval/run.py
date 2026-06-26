"""CLI for the safety eval harness.

    python -m core.eval.run                  # run, print, gate against baseline
    python -m core.eval.run --update-baseline

Once the baseline is frozen, any change that drops the safety pass-rate fails this
command (and the regression test) instead of shipping silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.eval.harness import EvalReport, regression, run

BASELINE_PATH = Path(__file__).parent / "baseline.json"
MIN_PASS_RATE = 1.0  # the deterministic safety layer must pass every golden check


def _print(report: EvalReport) -> None:
    d = report.to_dict()
    print(f"pass_rate: {d['pass_rate']:.3f}  ({d['passed']}/{d['total']})")
    for cat, rate in d["by_category"].items():
        print(f"  {cat:<10} {rate:.3f}")
    for name in d["failures"]:
        print(f"  FAIL: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AeroSense safety eval harness")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    report = run()
    _print(report)

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps({"pass_rate": report.pass_rate}, indent=2))
        print(f"\nBaseline updated -> {BASELINE_PATH}")
        return 0

    failures = []
    if report.pass_rate < MIN_PASS_RATE:
        failures.append(f"pass_rate {report.pass_rate:.3f} < required {MIN_PASS_RATE}")
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())["pass_rate"]
        msg = regression(report, baseline)
        if msg:
            failures.append(msg)

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS: safety eval green, no regression.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
