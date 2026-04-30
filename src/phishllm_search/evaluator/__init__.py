"""The fixed evaluator: ``evaluate(candidate, dataset) -> EvalResult``."""

from .runner import EvalResult, evaluate_candidate
from .metrics import bootstrap_recall_ci, classification_metrics
from .failures import FAILURE_BUCKET_KEYS, classify_failure
from .confusion import confusion_matrix

__all__ = [
    "EvalResult",
    "evaluate_candidate",
    "bootstrap_recall_ci",
    "classification_metrics",
    "FAILURE_BUCKET_KEYS",
    "classify_failure",
    "confusion_matrix",
]
