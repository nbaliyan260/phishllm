from __future__ import annotations

from phishllm_search.evaluator import evaluate_candidate
from phishllm_search.evaluator.failures import FAILURE_BUCKET_KEYS


def test_evaluator_runs_end_to_end(tiny_dataset, baseline_candidate):
    result = evaluate_candidate(baseline_candidate, tiny_dataset, bootstrap_iters=50)
    assert result.metrics["num_samples"] > 0
    assert 0.0 <= result.metrics["precision"] <= 1.0
    assert 0.0 <= result.metrics["recall"] <= 1.0


def test_evaluator_metrics_have_failure_buckets(tiny_dataset, baseline_candidate):
    result = evaluate_candidate(baseline_candidate, tiny_dataset, bootstrap_iters=50)
    buckets = result.metrics["failure_buckets"]
    for key in FAILURE_BUCKET_KEYS:
        assert key in buckets


def test_evaluator_is_deterministic(tiny_dataset, baseline_candidate):
    a = evaluate_candidate(baseline_candidate, tiny_dataset, bootstrap_iters=100, seed=3)
    b = evaluate_candidate(baseline_candidate, tiny_dataset, bootstrap_iters=100, seed=3)
    keys_to_compare = ["precision", "recall", "f1", "fpr", "fnr",
                       "median_runtime_sec", "estimated_cost_per_1k", "tp", "fp", "tn", "fn"]
    for key in keys_to_compare:
        assert a.metrics[key] == b.metrics[key], key


def test_confusion_matrix_sums_match_total(tiny_dataset, baseline_candidate):
    result = evaluate_candidate(baseline_candidate, tiny_dataset, bootstrap_iters=50)
    cm = result.metrics["confusion"]
    total = sum(cm[y][p] for y in cm for p in cm[y])
    assert total == result.metrics["num_samples"]
