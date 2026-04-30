from __future__ import annotations

from copy import deepcopy

from phishllm_search.schema import is_valid
from phishllm_search.search.proposers.base import ProposerContext
from phishllm_search.search.proposers.heuristic import HeuristicProposer
from phishllm_search.utils.hashing import candidate_hash


def _ctx(top_candidate, top_metrics, **kwargs):
    return ProposerContext(
        round_idx=1,
        seen_hashes={candidate_hash(top_candidate)},
        history=[top_metrics],
        top_candidates=[top_candidate],
        top_metrics=[top_metrics],
        diverse_candidate=None,
        failure_summary=kwargs.get("failure_summary", {}),
        precision_floor=0.95,
        runtime_budget_sec=6.0,
        cost_budget_per_1k=5.0,
    )


def test_heuristic_proposes_unique_valid_candidates(baseline_candidate):
    metrics = {"precision": 0.97, "recall": 0.6, "f1": 0.74,
               "median_runtime_sec": 4.0, "estimated_cost_per_1k": 1.5,
               "failure_buckets": {"crp_miss": 5}}
    proposer = HeuristicProposer(batch_size=5, seed=1)
    proposals = proposer.propose(_ctx(baseline_candidate, metrics,
                                      failure_summary={"crp_miss": 5}))
    assert len(proposals) >= 3
    seen_hashes = {candidate_hash(baseline_candidate)}
    for p in proposals:
        assert is_valid(p), p
        assert candidate_hash(p) not in seen_hashes
        seen_hashes.add(candidate_hash(p))


def test_heuristic_targets_recall_when_recall_low(baseline_candidate):
    metrics = {"precision": 0.99, "recall": 0.40, "f1": 0.55,
               "median_runtime_sec": 4.0, "estimated_cost_per_1k": 1.5,
               "failure_buckets": {"crp_miss": 10}}
    proposals = HeuristicProposer(batch_size=4, seed=2).propose(
        _ctx(baseline_candidate, metrics, failure_summary={"crp_miss": 10})
    )
    assert any(p.get("brand_prompt") == "brand_recall_v1" for p in proposals)


def test_heuristic_targets_precision_when_precision_breaches_floor(baseline_candidate):
    metrics = {"precision": 0.80, "recall": 0.85, "f1": 0.82,
               "median_runtime_sec": 4.0, "estimated_cost_per_1k": 1.5,
               "failure_buckets": {"alias_false_positive": 5}}
    proposals = HeuristicProposer(batch_size=4, seed=3).propose(
        _ctx(baseline_candidate, metrics, failure_summary={"alias_false_positive": 5})
    )
    assert any(p.get("brand_prompt") == "brand_precision_v1" for p in proposals)


def test_heuristic_respects_seen_hashes(baseline_candidate):
    metrics = {"precision": 0.99, "recall": 0.5, "f1": 0.6,
               "median_runtime_sec": 4.0, "estimated_cost_per_1k": 1.5,
               "failure_buckets": {"crp_miss": 1}}
    base_hash = candidate_hash(baseline_candidate)

    ctx = ProposerContext(
        round_idx=1,
        seen_hashes={base_hash},
        history=[metrics],
        top_candidates=[deepcopy(baseline_candidate)],
        top_metrics=[metrics],
        diverse_candidate=None,
        failure_summary={"crp_miss": 1},
    )
    proposals = HeuristicProposer(batch_size=4, seed=4).propose(ctx)
    for p in proposals:
        assert candidate_hash(p) != base_hash
