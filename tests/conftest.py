"""Test fixtures and import-path setup for the test suite."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest


@pytest.fixture(scope="session")
def tiny_dataset(tmp_path_factory):
    """Provide a small dataset on disk for evaluator tests."""
    from phishllm_search.genset import generate_dataset

    out = tmp_path_factory.mktemp("tiny_data")
    generate_dataset(out, seed=11, phishing_per_template=1, benign_per_template=1)
    return out


@pytest.fixture(scope="session")
def baseline_candidate():
    return {
        "name": "test_baseline",
        "backend": "mock",
        "brand_prompt": "brand_default_v1",
        "crp_prompt": "crp_default_v1",
        "use_logo_ocr": True,
        "use_logo_caption": True,
        "prompt_defense": True,
        "popularity_validation": "google-indexed",
        "hosting_rule": "strict",
        "max_interactions": 1,
        "brand_confidence_min": 0.80,
        "report_policy": "mismatch_and_crp",
        "temperature": 0.0,
        "runtime_budget_sec": 6.0,
    }
