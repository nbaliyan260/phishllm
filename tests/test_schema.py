from __future__ import annotations

from copy import deepcopy

import pytest

from phishllm_search.schema import (
    CandidateValidationError,
    is_valid,
    schema_summary,
    validate,
    validate_many,
)


def test_baseline_candidate_validates(baseline_candidate):
    validate(baseline_candidate)
    assert is_valid(baseline_candidate)


@pytest.mark.parametrize("field,value", [
    ("backend", "openai-gpt35"),
    ("brand_prompt", "brand_unknown_v1"),
    ("popularity_validation", "yes_please"),
    ("max_interactions", 5),
    ("brand_confidence_min", 1.5),
    ("report_policy", "always_phish"),
])
def test_invalid_enum_or_range(baseline_candidate, field, value):
    bad = deepcopy(baseline_candidate)
    bad[field] = value
    assert not is_valid(bad)
    with pytest.raises(CandidateValidationError):
        validate(bad)


def test_missing_required_field(baseline_candidate):
    bad = deepcopy(baseline_candidate)
    bad.pop("backend")
    with pytest.raises(CandidateValidationError):
        validate(bad)


def test_validate_many_partitions_correctly(baseline_candidate):
    bad = deepcopy(baseline_candidate)
    bad["backend"] = "openai-gpt35"
    valid, errors = validate_many([baseline_candidate, bad])
    assert len(valid) == 1
    assert len(errors) == 1


def test_schema_summary_mentions_required_fields():
    summary = schema_summary()
    for key in ("backend", "brand_prompt", "max_interactions", "report_policy"):
        assert key in summary
