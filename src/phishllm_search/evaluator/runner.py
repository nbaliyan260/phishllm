"""``evaluate(candidate, dataset)`` -- the fixed evaluation contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..backends import make_backend
from ..backends.base import Prediction
from ..dataset import Sample, load_samples
from ..schema import validate
from .confusion import confusion_matrix
from .failures import classify_failure, empty_buckets
from .metrics import (
    bootstrap_recall_ci,
    classification_metrics,
    median,
    percentile,
)


@dataclass
class EvalResult:
    """Self-describing output of one evaluation run."""

    metrics: Dict[str, Any]
    rows: List[Dict[str, Any]] = field(default_factory=list)
    candidate: Dict[str, Any] = field(default_factory=dict)

    @property
    def precision(self) -> float:
        return float(self.metrics["precision"])

    @property
    def recall(self) -> float:
        return float(self.metrics["recall"])


def _row_for(sample: Sample, pred: Prediction, failure: Optional[str]) -> Dict[str, Any]:
    return {
        "site_id": sample.site_id,
        "url": sample.url,
        "true_label": sample.label,
        "pred_label": pred.pred_label,
        "target_brand": sample.target_brand,
        "pred_brand": pred.pred_brand or "",
        "brand_confidence": round(pred.brand_confidence, 4),
        "brand_source": pred.brand_source,
        "crp": int(pred.crp),
        "is_crp_true": int(sample.is_crp),
        "crp_reason": pred.crp_reason,
        "reasons": "|".join(pred.reasons),
        "runtime_sec": round(pred.runtime_sec, 4),
        "estimated_cost": round(pred.estimated_cost, 6),
        "failure_bucket": failure or "",
        "notes": sample.notes,
    }


def evaluate_candidate(
    candidate: Dict[str, Any],
    dataset_dir: Path,
    bootstrap_iters: int = 1000,
    seed: int = 0,
) -> EvalResult:
    """Run the full per-page pipeline for one candidate and aggregate metrics.

    The function is deterministic for the mock backend. Per-sample exceptions
    are caught and routed into the ``api_or_parser_failure`` bucket so the
    search loop is not derailed by a single broken backend call.
    """
    validate(candidate)
    samples = load_samples(Path(dataset_dir))
    backend = make_backend(candidate)

    failures = empty_buckets()
    rows: List[Dict[str, Any]] = []
    true_labels: List[str] = []
    pred_labels: List[str] = []
    runtimes: List[float] = []
    costs: List[float] = []

    for sample in samples:
        try:
            pred = backend.predict(sample, candidate)
        except Exception as exc:
            pred = Prediction(
                pred_label="benign",
                pred_brand=None,
                brand_confidence=0.0,
                brand_source="error",
                crp=False,
                crp_reason="api_or_parser_failure",
                reasons=[f"error:{type(exc).__name__}:{exc}"],
                runtime_sec=0.0,
                estimated_cost=0.0,
            )
            failures["api_or_parser_failure"] += 1

        bucket = classify_failure(sample, pred)
        if bucket is not None:
            failures[bucket] = failures.get(bucket, 0) + 1

        rows.append(_row_for(sample, pred, bucket))
        true_labels.append(sample.label)
        pred_labels.append(pred.pred_label)
        runtimes.append(pred.runtime_sec)
        costs.append(pred.estimated_cost)

    cm = classification_metrics(true_labels, pred_labels)
    recall_lo, recall_hi = bootstrap_recall_ci(
        true_labels, pred_labels, iterations=bootstrap_iters, seed=seed
    )

    metrics: Dict[str, Any] = {
        "candidate_name": candidate.get("name", "unnamed"),
        "num_samples": len(samples),
        **cm.to_dict(),
        "recall_ci_lo": round(recall_lo, 4),
        "recall_ci_hi": round(recall_hi, 4),
        "median_runtime_sec": round(median(runtimes), 4),
        "p95_runtime_sec": round(percentile(runtimes, 95), 4),
        "estimated_cost_per_1k": round(sum(costs) / len(costs) * 1000.0 if costs else 0.0, 4),
        "failure_buckets": failures,
        "confusion": confusion_matrix(true_labels, pred_labels),
        "respects_precision_floor": cm.precision >= 0.95,
        "respects_runtime_budget": median(runtimes) <= float(candidate.get("runtime_budget_sec", 6.0)),
    }
    return EvalResult(metrics=metrics, rows=rows, candidate=dict(candidate))
