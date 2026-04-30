from __future__ import annotations

from phishllm_search.backends.base import Prediction
from phishllm_search.dataset import Sample
from phishllm_search.evaluator.failures import (
    FAILURE_BUCKET_KEYS,
    classify_failure,
    empty_buckets,
)


def _sample(label="phish", target="paypal.com", notes=""):
    return Sample(
        site_id="site_001",
        url="https://paypal-secure.top/",
        html="<html><body>password</body></html>",
        label=label,
        target_brand=target,
        is_crp=1,
        notes=notes,
    )


def _pred(**kwargs):
    base = dict(
        pred_label="phish",
        pred_brand="paypal.com",
        brand_confidence=0.9,
        brand_source="ocr+caption",
        crp=True,
        crp_reason="crp_terms",
        reasons=[],
        runtime_sec=0.5,
        estimated_cost=0.001,
    )
    base.update(kwargs)
    return Prediction(**base)


def test_no_failure_when_correct():
    assert classify_failure(_sample(), _pred()) is None


def test_alias_false_positive_detected():
    s = _sample(label="benign")
    p = _pred(pred_label="phish", reasons=["alias_false_positive"])
    assert classify_failure(s, p) == "alias_false_positive"


def test_prompt_injection_failure_detected():
    p = _pred(pred_label="benign", crp=False, crp_reason="prompt_injection_failure")
    assert classify_failure(_sample(), p) == "prompt_injection_failure"


def test_brand_miss_detected():
    p = _pred(pred_label="benign", pred_brand=None, crp=True, crp_reason="crp_terms")
    assert classify_failure(_sample(label="phish"), p) == "brand_miss"


def test_crp_miss_detected():
    p = _pred(pred_label="benign", pred_brand="paypal.com", crp=False, crp_reason="no_crp_terms")
    assert classify_failure(_sample(label="phish"), p) == "crp_miss"


def test_fusion_miss_detected_when_brand_and_crp_present():
    p = _pred(pred_label="benign", pred_brand="paypal.com", crp=True, crp_reason="crp_terms")
    assert classify_failure(_sample(label="phish"), p) == "fusion_miss"


def test_hidden_login_miss_detected():
    s = _sample(label="phish", notes="hidden login behind continue button")
    p = _pred(pred_label="benign", crp=False, crp_reason="no_crp_terms")
    assert classify_failure(s, p) == "hidden_login_miss"


def test_brand_hallucination_detected():
    s = _sample(label="benign", target="microsoft.com")
    p = _pred(pred_label="phish", pred_brand="paypal.com")
    assert classify_failure(s, p) == "brand_hallucination"


def test_empty_buckets_has_all_keys():
    buckets = empty_buckets()
    assert set(buckets.keys()) == set(FAILURE_BUCKET_KEYS)
    assert all(v == 0 for v in buckets.values())
