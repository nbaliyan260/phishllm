"""Confusion-matrix utilities used by the reporting layer."""

from __future__ import annotations

from typing import Dict, Iterable, List


_LABELS = ("benign", "phish")


def confusion_matrix(true_labels: Iterable[str], pred_labels: Iterable[str]) -> Dict[str, Dict[str, int]]:
    """Return a nested dict ``{true: {pred: count}}`` with both labels present."""
    matrix: Dict[str, Dict[str, int]] = {y: {p: 0 for p in _LABELS} for y in _LABELS}
    for y, p in zip(true_labels, pred_labels):
        if y not in _LABELS or p not in _LABELS:
            continue
        matrix[y][p] += 1
    return matrix


def confusion_matrix_lines(matrix: Dict[str, Dict[str, int]]) -> List[str]:
    """Pretty-print the confusion matrix as a 3-line block."""
    header = "             pred=benign   pred=phish"
    rows = [header]
    for y in _LABELS:
        rows.append(f"true={y:6s}  {matrix[y]['benign']:>10d}   {matrix[y]['phish']:>10d}")
    return rows
