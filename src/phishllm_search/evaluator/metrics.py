"""Metric helpers used by the evaluator and reporting layer."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class ClassificationMetrics:
    """Aggregate classification metrics for a single candidate."""

    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def fpr(self) -> float:
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) else 0.0

    @property
    def fnr(self) -> float:
        return self.fn / (self.fn + self.tp) if (self.fn + self.tp) else 0.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.tn + self.fn
        return (self.tp + self.tn) / total if total else 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "fpr": round(self.fpr, 4),
            "fnr": round(self.fnr, 4),
            "accuracy": round(self.accuracy, 4),
        }


def classification_metrics(true_labels: Iterable[str], pred_labels: Iterable[str]) -> ClassificationMetrics:
    """Aggregate confusion-matrix counts for the binary phish/benign task."""
    tp = fp = tn = fn = 0
    for y, p in zip(true_labels, pred_labels):
        if y == "phish" and p == "phish":
            tp += 1
        elif y == "benign" and p == "phish":
            fp += 1
        elif y == "benign" and p == "benign":
            tn += 1
        else:
            fn += 1
    return ClassificationMetrics(tp=tp, fp=fp, tn=tn, fn=fn)


def bootstrap_recall_ci(
    true_labels: List[str],
    pred_labels: List[str],
    iterations: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> Tuple[float, float]:
    """Percentile-bootstrap CI for the recall (phish-class only).

    Returns ``(lower, upper)`` recall bounds. Uses Python's stdlib ``random``
    so the CI is reproducible without numpy.
    """
    rng = random.Random(seed)
    pairs = list(zip(true_labels, pred_labels))
    if not pairs:
        return 0.0, 0.0
    n = len(pairs)
    recalls: List[float] = []
    for _ in range(iterations):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        tp = sum(1 for y, p in sample if y == "phish" and p == "phish")
        fn = sum(1 for y, p in sample if y == "phish" and p == "benign")
        denom = tp + fn
        recalls.append(tp / denom if denom else 0.0)
    recalls.sort()
    lo_idx = max(0, int((alpha / 2) * iterations))
    hi_idx = min(iterations - 1, int((1 - alpha / 2) * iterations))
    return recalls[lo_idx], recalls[hi_idx]


def median(values: Iterable[float]) -> float:
    seq = sorted(values)
    n = len(seq)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return seq[mid]
    return (seq[mid - 1] + seq[mid]) / 2.0


def percentile(values: Iterable[float], q: float) -> float:
    seq = sorted(values)
    if not seq:
        return 0.0
    if not 0 <= q <= 100:
        raise ValueError("q must be in [0, 100]")
    k = (len(seq) - 1) * (q / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return seq[int(k)]
    return seq[lo] + (k - lo) * (seq[hi] - seq[lo])
