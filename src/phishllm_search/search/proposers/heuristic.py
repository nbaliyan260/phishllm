"""Heuristic mutation proposer.

This proposer is the deterministic, dependency-free fallback used in CI and
when no LLM API key is configured. It applies a small library of mutations to
the current top candidate and to a diverse under-performer, biasing the
mutation choice by the dominant failure bucket. The bias is what makes it a
real "search" rather than a random walk -- the same data the LLM proposer
sees is also consumed here.
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Dict, List

from ...utils.hashing import candidate_hash
from .base import Proposer, ProposerContext


_THRESHOLDS = (0.70, 0.75, 0.80, 0.85, 0.90)
_BRAND_PROMPTS = ("brand_default_v1", "brand_recall_v1", "brand_precision_v1", "brand_robust_v1")
_CRP_PROMPTS = ("crp_default_v1", "crp_recall_v1", "crp_precision_v1", "crp_robust_v1")
_POPULARITY = ("google-indexed", "cached", "disabled")


class HeuristicProposer:
    def __init__(self, batch_size: int = 6, seed: int = 0) -> None:
        self.batch_size = batch_size
        self._rng = random.Random(seed)

    def propose(self, ctx: ProposerContext) -> List[Dict[str, Any]]:
        if not ctx.top_candidates:
            return []
        top = ctx.top_candidates[0]
        top_metrics = ctx.top_metrics[0] if ctx.top_metrics else {}

        bias = _failure_bias(ctx.failure_summary, top_metrics, ctx.precision_floor)
        proposals: List[Dict[str, Any]] = []

        for mutation in _ordered_mutations(bias):
            cand = deepcopy(top)
            cand.pop("hypothesis", None)
            mutation(cand, self._rng)
            cand["name"] = f"round{ctx.round_idx}_{_short_descriptor(cand, top)}"
            cand["hypothesis"] = _hypothesis_for(bias, cand, top)
            proposals.append(cand)

        if ctx.diverse_candidate:
            div = deepcopy(ctx.diverse_candidate)
            div.pop("hypothesis", None)
            _mutate_recall(div, self._rng)
            div["name"] = f"round{ctx.round_idx}_diverse_recall"
            div["hypothesis"] = (
                "Re-test the previously diverse low-performer with a recall-leaning "
                "patch to see whether the search has missed a useful frontier point."
            )
            proposals.append(div)

        unique: List[Dict[str, Any]] = []
        seen_local = set()
        for cand in proposals:
            h = candidate_hash(cand)
            if h in ctx.seen_hashes or h in seen_local:
                continue
            seen_local.add(h)
            unique.append(cand)
            if len(unique) >= self.batch_size:
                break
        return unique


def _failure_bias(buckets: Dict[str, int], top_metrics: Dict[str, Any], precision_floor: float) -> str:
    if top_metrics:
        if float(top_metrics.get("precision", 1.0)) < precision_floor:
            return "precision"
        if buckets.get("prompt_injection_failure", 0) > 0:
            return "robustness"
        if buckets.get("alias_false_positive", 0) > 0:
            return "validation"
        if buckets.get("crp_miss", 0) + buckets.get("hidden_login_miss", 0) > 0:
            return "recall"
        if float(top_metrics.get("estimated_cost_per_1k", 0.0)) > 5.0:
            return "cost"
    return "recall"


def _ordered_mutations(bias: str):
    base = [
        _mutate_recall,
        _mutate_precision,
        _mutate_robustness,
        _mutate_validation,
        _mutate_cost,
        _mutate_threshold,
        _mutate_policy,
    ]
    priority = {
        "recall":      [_mutate_recall, _mutate_threshold, _mutate_policy, _mutate_robustness],
        "precision":   [_mutate_precision, _mutate_threshold, _mutate_validation, _mutate_robustness],
        "robustness":  [_mutate_robustness, _mutate_validation, _mutate_precision, _mutate_recall],
        "validation":  [_mutate_validation, _mutate_robustness, _mutate_precision, _mutate_threshold],
        "cost":        [_mutate_cost, _mutate_threshold, _mutate_policy, _mutate_recall],
    }[bias]
    seen = set()
    ordered = []
    for fn in priority + base:
        if id(fn) not in seen:
            ordered.append(fn)
            seen.add(id(fn))
    return ordered


def _mutate_recall(cand: Dict[str, Any], rng: random.Random) -> None:
    cand["brand_prompt"] = "brand_recall_v1"
    cand["crp_prompt"] = "crp_recall_v1"
    cand["report_policy"] = "mismatch_or_crp"
    cand["max_interactions"] = max(int(cand.get("max_interactions", 0)), 1)
    cand["brand_confidence_min"] = round(min(0.80, max(0.70, float(cand.get("brand_confidence_min", 0.8)) - 0.05)), 2)


def _mutate_precision(cand: Dict[str, Any], rng: random.Random) -> None:
    cand["brand_prompt"] = "brand_precision_v1"
    cand["crp_prompt"] = "crp_precision_v1"
    cand["report_policy"] = "mismatch_and_crp"
    cand["popularity_validation"] = "google-indexed"
    cand["brand_confidence_min"] = round(min(0.95, float(cand.get("brand_confidence_min", 0.8)) + 0.05), 2)


def _mutate_robustness(cand: Dict[str, Any], rng: random.Random) -> None:
    cand["brand_prompt"] = "brand_robust_v1"
    cand["crp_prompt"] = "crp_robust_v1"
    cand["prompt_defense"] = True


def _mutate_validation(cand: Dict[str, Any], rng: random.Random) -> None:
    cand["popularity_validation"] = "google-indexed"
    cand["hosting_rule"] = "strict"


def _mutate_cost(cand: Dict[str, Any], rng: random.Random) -> None:
    cand["use_logo_caption"] = False
    cand["popularity_validation"] = "cached"
    cand["max_interactions"] = 0


def _mutate_threshold(cand: Dict[str, Any], rng: random.Random) -> None:
    current = float(cand.get("brand_confidence_min", 0.80))
    options = [t for t in _THRESHOLDS if abs(t - current) > 1e-6]
    cand["brand_confidence_min"] = rng.choice(options) if options else current


def _mutate_policy(cand: Dict[str, Any], rng: random.Random) -> None:
    current = cand.get("report_policy", "mismatch_and_crp")
    options = [p for p in ("mismatch_and_crp", "mismatch_or_crp", "score_only") if p != current]
    cand["report_policy"] = rng.choice(options)


def _short_descriptor(cand: Dict[str, Any], parent: Dict[str, Any]) -> str:
    bits: List[str] = []
    if cand.get("brand_prompt") != parent.get("brand_prompt"):
        bits.append(cand["brand_prompt"].split("_v")[0])
    if cand.get("crp_prompt") != parent.get("crp_prompt"):
        bits.append(cand["crp_prompt"].split("_v")[0])
    if cand.get("popularity_validation") != parent.get("popularity_validation"):
        bits.append(f"pv-{cand['popularity_validation']}")
    if cand.get("hosting_rule") != parent.get("hosting_rule"):
        bits.append(f"host-{cand['hosting_rule']}")
    if cand.get("max_interactions") != parent.get("max_interactions"):
        bits.append(f"int{cand['max_interactions']}")
    if cand.get("report_policy") != parent.get("report_policy"):
        bits.append(cand["report_policy"])
    if abs(float(cand.get("brand_confidence_min", 0.8)) - float(parent.get("brand_confidence_min", 0.8))) > 1e-6:
        bits.append(f"thr{int(cand['brand_confidence_min']*100)}")
    return "-".join(bits) or "tweak"


def _hypothesis_for(bias: str, cand: Dict[str, Any], parent: Dict[str, Any]) -> str:
    return {
        "recall":     "Heuristic mutation targeting recall: lower threshold, OR-fusion, recall prompts.",
        "precision":  "Heuristic mutation targeting precision: higher threshold, AND-fusion, precision prompts.",
        "robustness": "Heuristic mutation targeting prompt-injection / typosquat resistance.",
        "validation": "Heuristic mutation targeting alias-FP via popularity validation and strict hosting.",
        "cost":       "Heuristic mutation targeting cost: cached validation, no caption, no transitions.",
    }.get(bias, "Heuristic mutation of the current top candidate.")
