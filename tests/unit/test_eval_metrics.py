"""Eval metric tests — binary classification math + pass-rate, with edge cases."""

import math

import pytest

from core.eval.metrics import (
    BinaryMetrics,
    confusion_matrix,
    evaluate_binary,
    pass_rate,
)


def test_confusion_matrix_basic():
    assert confusion_matrix([True, True, False, False],
                            [True, False, True, False]) == (1, 1, 1, 1)


def test_confusion_matrix_length_mismatch_raises():
    with pytest.raises(ValueError, match="length mismatch"):
        confusion_matrix([True], [True, False])


def test_perfect_classifier():
    m = evaluate_binary([True, False, True], [True, False, True])
    assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0 and m.accuracy == 1.0


def test_known_values():
    m = evaluate_binary([True, True, False, False], [True, False, False, False])
    assert (m.tp, m.fp, m.tn, m.fn) == (1, 0, 2, 1)
    assert m.precision == 1.0
    assert m.recall == 0.5
    assert math.isclose(m.f1, 2 * 1.0 * 0.5 / 1.5)
    assert m.accuracy == 0.75


def test_empty_no_crash():
    m = evaluate_binary([], [])
    assert m.precision == 0.0 and m.f1 == 0.0 and m.support == 0


def test_precision_zero_when_no_positive_predictions():
    assert evaluate_binary([True, True], [False, False]).precision == 0.0


def test_recall_zero_when_no_actual_positives():
    assert evaluate_binary([False, False], [True, False]).recall == 0.0


def test_accuracy_half():
    assert evaluate_binary([True, False], [True, True]).accuracy == 0.5


def test_metrics_to_dict_keys():
    d = evaluate_binary([True], [True]).to_dict()
    assert set(d) == {"tp", "fp", "tn", "fn", "precision", "recall",
                      "f1", "accuracy", "support"}


def test_metrics_frozen():
    m = evaluate_binary([True], [True])
    with pytest.raises(Exception):
        m.precision = 0.0  # type: ignore[misc]


def test_pass_rate_all_pass():
    assert pass_rate([True, True, True]) == 1.0


def test_pass_rate_partial():
    assert pass_rate([True, False, True, False]) == 0.5


def test_pass_rate_all_fail():
    assert pass_rate([False, False]) == 0.0


def test_pass_rate_empty_is_zero():
    assert pass_rate([]) == 0.0


def test_demo_self_check():
    from core.eval.metrics import demo
    demo()


@pytest.mark.parametrize("yt,yp,f1", [
    ([True, True], [True, True], 1.0),
    ([True, False], [False, True], 0.0),
])
def test_f1_parametrized(yt, yp, f1):
    assert math.isclose(evaluate_binary(yt, yp).f1, f1)
