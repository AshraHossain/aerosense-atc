"""Eval metrics — stdlib only (ported from the AutoRedTeam eval harness).

AeroOps M1 evaluates the *deterministic safety layer* (the routers) against golden
scenarios, where every expected outcome is known — so a pass-rate over checks plus
binary precision/recall is honest, not LLM-judge guesswork. The binary metrics are
kept for M1+ when a Gemini model-version bump must be gated against a baseline.
No scikit-learn: this is arithmetic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BinaryMetrics:
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    support: int

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def confusion_matrix(y_true: list[bool], y_pred: list[bool]) -> tuple[int, int, int, int]:
    if len(y_true) != len(y_pred):
        raise ValueError(f"length mismatch: {len(y_true)} != {len(y_pred)}")
    tp = fp = tn = fn = 0
    for actual, predicted in zip(y_true, y_pred):
        if actual and predicted:
            tp += 1
        elif not actual and predicted:
            fp += 1
        elif not actual and not predicted:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def evaluate_binary(y_true: list[bool], y_pred: list[bool]) -> BinaryMetrics:
    tp, fp, tn, fn = confusion_matrix(y_true, y_pred)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(tp + tn, tp + fp + tn + fn)
    return BinaryMetrics(tp, fp, tn, fn, precision, recall, f1, accuracy, len(y_true))


def pass_rate(results: list[bool]) -> float:
    """Fraction of checks that passed. Empty → 0.0 (no evidence of correctness)."""
    return _safe_div(sum(1 for r in results if r), len(results))


def demo() -> None:
    """Self-check."""
    m = evaluate_binary([True, True, False, False], [True, False, False, False])
    assert (m.tp, m.fp, m.tn, m.fn) == (1, 0, 2, 1), m
    assert m.precision == 1.0 and m.recall == 0.5
    assert pass_rate([True, True, False, True]) == 0.75
    assert pass_rate([]) == 0.0
    print("metrics.demo OK")


if __name__ == "__main__":
    demo()
