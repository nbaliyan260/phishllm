"""Failure-bucket classification.

The PhishLLM paper distinguishes several qualitatively different ways a
detector can be wrong. We reproduce the most informative buckets here so the
search loop can give the LLM proposer (and the human reader) actionable
feedback rather than just an aggregate F1 number.
"""

from __future__ import annotations

from typing import Dict, Optional

from ..dataset import Sample
from ..backends.base import Prediction


FAILURE_BUCKET_KEYS = (
    "brand_hallucination",
    "alias_false_positive",
    "brand_miss",
    "crp_miss",
    "hidden_login_miss",
    "fusion_miss",
    "prompt_injection_failure",
    "api_or_parser_failure",
)


def classify_failure(sample: Sample, pred: Prediction) -> Optional[str]:
    """Return the failure bucket triggered by this sample, if any.

    ``None`` is returned when the prediction is correct or when the error is
    not attributable to one of the tracked buckets. The order matters --
    earlier checks are higher priority because they correspond to more
    specific (and more actionable) failure modes.
    """
    true_label = sample.label
    pred_label = pred.pred_label

    if true_label == "benign" and pred_label == "phish":
        if "alias_false_positive" in pred.reasons:
            return "alias_false_positive"
        if pred.pred_brand:
            target = (sample.target_brand or "").strip()
            if not target or pred.pred_brand != target:
                return "brand_hallucination"

    if true_label == "phish" and pred_label == "benign":
        if pred.crp_reason == "prompt_injection_failure":
            return "prompt_injection_failure"
        notes = (sample.notes or "").lower()
        if "hidden" in notes or "transition" in notes:
            return "hidden_login_miss"
        if pred.pred_brand is None:
            return "brand_miss"
        if not pred.crp:
            return "crp_miss"
        return "fusion_miss"

    return None


def empty_buckets() -> Dict[str, int]:
    return {k: 0 for k in FAILURE_BUCKET_KEYS}
