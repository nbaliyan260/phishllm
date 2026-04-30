from __future__ import annotations

import math

import pytest

from phishllm_search.evaluator.metrics import (
    bootstrap_recall_ci,
    classification_metrics,
    median,
    percentile,
)


def test_classification_metrics_perfect():
    cm = classification_metrics(["phish", "phish", "benign", "benign"],
                                 ["phish", "phish", "benign", "benign"])
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.f1 == 1.0
    assert cm.accuracy == 1.0
    assert cm.fpr == 0.0
    assert cm.fnr == 0.0


def test_classification_metrics_mixed():
    cm = classification_metrics(["phish", "phish", "benign", "benign"],
                                 ["phish", "benign", "phish", "benign"])
    assert cm.tp == 1 and cm.fp == 1 and cm.tn == 1 and cm.fn == 1
    assert math.isclose(cm.precision, 0.5)
    assert math.isclose(cm.recall, 0.5)
    assert math.isclose(cm.f1, 0.5)


def test_classification_metrics_empty():
    cm = classification_metrics([], [])
    assert cm.precision == 0.0
    assert cm.recall == 0.0
    assert cm.f1 == 0.0


def test_bootstrap_ci_bounds():
    true_labels = ["phish"] * 50 + ["benign"] * 50
    pred_labels = ["phish"] * 40 + ["benign"] * 10 + ["phish"] * 5 + ["benign"] * 45
    lo, hi = bootstrap_recall_ci(true_labels, pred_labels, iterations=200, seed=1)
    assert 0.0 <= lo <= hi <= 1.0
    assert hi - lo > 0  # actual bootstrap variance


def test_bootstrap_ci_is_deterministic():
    true_labels = ["phish", "benign", "phish", "benign"] * 5
    pred_labels = ["phish", "benign", "benign", "benign"] * 5
    a = bootstrap_recall_ci(true_labels, pred_labels, iterations=100, seed=42)
    b = bootstrap_recall_ci(true_labels, pred_labels, iterations=100, seed=42)
    assert a == b


def test_median_and_percentile():
    seq = [1, 2, 3, 4, 5]
    assert median(seq) == 3
    assert median([1, 2]) == 1.5
    assert percentile(seq, 50) == 3
    assert percentile(seq, 0) == 1
    assert percentile(seq, 100) == 5


def test_percentile_rejects_invalid_q():
    with pytest.raises(ValueError):
        percentile([1, 2, 3], 105)
