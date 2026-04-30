from __future__ import annotations

import json
from pathlib import Path

import pytest

from phishllm_search.search.loop import SearchConfig, run_search
from phishllm_search.search.selector import (
    diverse_candidate,
    pareto_frontier,
    precision_floor_selector,
)
from phishllm_search.search.stopping import (
    StopReason,
    StoppingState,
    evaluate_stopping,
)


def test_precision_floor_orders_correctly():
    a = {"candidate": {"name": "a"}, "metrics": {"precision": 0.99, "recall": 0.5,
                                                  "f1": 0.6, "median_runtime_sec": 1.0,
                                                  "estimated_cost_per_1k": 1.0}}
    b = {"candidate": {"name": "b"}, "metrics": {"precision": 0.80, "recall": 0.95,
                                                  "f1": 0.87, "median_runtime_sec": 1.0,
                                                  "estimated_cost_per_1k": 1.0}}
    ranked = precision_floor_selector([b, a], precision_floor=0.95)
    assert ranked[0]["candidate"]["name"] == "a"


def test_pareto_frontier_filters_dominated():
    pts = [
        {"candidate": {"name": "lo"}, "metrics": {"recall": 0.5, "median_runtime_sec": 1.0, "estimated_cost_per_1k": 1.0}},
        {"candidate": {"name": "mid"}, "metrics": {"recall": 0.7, "median_runtime_sec": 2.0, "estimated_cost_per_1k": 2.0}},
        {"candidate": {"name": "hi"}, "metrics": {"recall": 0.6, "median_runtime_sec": 3.0, "estimated_cost_per_1k": 3.0}},
    ]
    frontier = {r["candidate"]["name"] for r in pareto_frontier(pts)}
    assert "hi" not in frontier
    assert "lo" in frontier and "mid" in frontier


def test_stopping_terminates_on_no_progress():
    state = StoppingState(best_recall_under_floor=0.6)
    result = evaluate_stopping(state, best_recall_this_round=0.601,
                               new_candidates_this_round=4, round_idx=1, max_rounds=5)
    assert result == StopReason.NOT_STOPPED
    state.rounds_without_gain = 1
    result = evaluate_stopping(state, best_recall_this_round=0.602,
                               new_candidates_this_round=4, round_idx=2, max_rounds=5)
    assert result == StopReason.NO_RECALL_GAIN


def test_stopping_terminates_on_max_rounds():
    state = StoppingState()
    result = evaluate_stopping(state, best_recall_this_round=0.9,
                               new_candidates_this_round=4, round_idx=5, max_rounds=5)
    assert result == StopReason.MAX_ROUNDS


def test_search_loop_end_to_end(tmp_path: Path, tiny_dataset: Path):
    seeds_root = tmp_path / "seeds"
    seeds_root.mkdir()
    for name, override in [
        ("baseline", {}),
        ("recall", {"brand_prompt": "brand_recall_v1", "report_policy": "mismatch_or_crp",
                    "brand_confidence_min": 0.70}),
    ]:
        candidate = {
            "name": name,
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
        candidate.update(override)
        (seeds_root / f"{name}.json").write_text(json.dumps(candidate, indent=2))

    cfg = SearchConfig(
        dataset_dir=tiny_dataset,
        candidate_dir=seeds_root,
        out_dir=tmp_path / "out",
        rounds=1,
        proposer="heuristic",
        seed=5,
        bootstrap_iters=50,
    )
    summary = run_search(cfg)
    assert summary["rounds_run"] >= 1
    assert (cfg.out_dir / "search_summary.csv").exists()
    assert (cfg.out_dir / "events.jsonl").exists()
    assert (cfg.out_dir / "top5.json").exists()


def test_diverse_candidate_returns_lowest_scoring():
    pts = [
        {"candidate": {"name": "good"}, "metrics": {"precision": 0.99, "recall": 0.9, "f1": 0.94,
                                                     "median_runtime_sec": 1.0, "estimated_cost_per_1k": 1.0,
                                                     "num_samples": 10}},
        {"candidate": {"name": "bad"}, "metrics": {"precision": 0.50, "recall": 0.4, "f1": 0.44,
                                                    "median_runtime_sec": 1.0, "estimated_cost_per_1k": 1.0,
                                                    "num_samples": 10}},
    ]
    div = diverse_candidate(pts)
    assert div is not None
    assert div["name"] == "bad"
