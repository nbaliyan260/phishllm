"""Top-level search loop.

Public entry point: :func:`run_search`. The loop:

1. Loads seed candidates and the dataset.
2. Evaluates every seed (round 0).
3. Selects top candidates and asks the proposer for new ones.
4. Evaluates new candidates (rounds 1..max_rounds).
5. Applies stopping criteria.
6. Persists structured logs, per-round metrics, and a final summary CSV.
"""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..dataset import load_samples
from ..evaluator import evaluate_candidate
from ..evaluator.failures import empty_buckets
from ..schema import validate
from ..utils.hashing import candidate_hash
from ..utils.logging import JsonlWriter, get_logger
from .proposers.base import Proposer, ProposerContext
from .proposers.heuristic import HeuristicProposer
from .proposers.llm import LLMProposer, LLMProposerConfig
from .selector import diverse_candidate, pareto_frontier, precision_floor_selector
from .stopping import StopReason, StoppingState, evaluate_stopping


_LOGGER = get_logger("search")


@dataclass
class SearchConfig:
    dataset_dir: Path
    candidate_dir: Path
    out_dir: Path
    rounds: int = 4
    proposer: str = "heuristic"
    precision_floor: float = 0.95
    runtime_budget_sec: float = 6.0
    cost_budget_per_1k: float = 5.0
    seed: int = 7
    bootstrap_iters: int = 1000
    keep_top_k: int = 3
    keep_frontier_k: int = 2

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SearchConfig":
        return cls(
            dataset_dir=Path(d["dataset_dir"]),
            candidate_dir=Path(d["candidate_dir"]),
            out_dir=Path(d["out_dir"]),
            rounds=int(d.get("rounds", 4)),
            proposer=str(d.get("proposer", "heuristic")),
            precision_floor=float(d.get("precision_floor", 0.95)),
            runtime_budget_sec=float(d.get("runtime_budget_sec", 6.0)),
            cost_budget_per_1k=float(d.get("cost_budget_per_1k", 5.0)),
            seed=int(d.get("seed", 7)),
            bootstrap_iters=int(d.get("bootstrap_iters", 1000)),
            keep_top_k=int(d.get("keep_top_k", 3)),
            keep_frontier_k=int(d.get("keep_frontier_k", 2)),
        )


def _load_seed_candidates(candidate_dir: Path) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for path in sorted(candidate_dir.glob("*.json")):
        cand = json.loads(path.read_text(encoding="utf-8"))
        validate(cand)
        candidates.append(cand)
    if not candidates:
        raise FileNotFoundError(f"No seed candidates in {candidate_dir}")
    return candidates


def _make_proposer(name: str, batch_size: int, seed: int) -> Proposer:
    if name == "heuristic":
        return HeuristicProposer(batch_size=batch_size, seed=seed)
    if name == "llm":
        return LLMProposer(config=LLMProposerConfig(batch_size=batch_size, fallback_seed=seed))
    raise ValueError(f"Unknown proposer: {name!r}")


def _aggregate_failure_buckets(round_results: List[Dict[str, Any]]) -> Dict[str, int]:
    aggregate = empty_buckets()
    for r in round_results:
        for k, v in r["metrics"].get("failure_buckets", {}).items():
            aggregate[k] = aggregate.get(k, 0) + int(v)
    return aggregate


def _evaluate_pool(
    pool: List[Dict[str, Any]],
    cfg: SearchConfig,
    round_idx: int,
    history: List[Dict[str, Any]],
    seen: set[str],
    events: JsonlWriter,
    out_dir: Path,
) -> List[Dict[str, Any]]:
    round_results: List[Dict[str, Any]] = []
    for cand in pool:
        validate(cand)
        h = candidate_hash(cand)
        if h in seen:
            continue
        seen.add(h)

        result = evaluate_candidate(
            cand,
            cfg.dataset_dir,
            bootstrap_iters=cfg.bootstrap_iters,
            seed=cfg.seed + round_idx,
        )
        record = {"candidate": dict(cand), "metrics": dict(result.metrics)}
        round_results.append(record)
        history.append({"round": round_idx, "name": cand["name"], **result.metrics})

        cand_dir = out_dir / f"round_{round_idx}" / cand["name"]
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "candidate.json").write_text(json.dumps(cand, indent=2), encoding="utf-8")
        (cand_dir / "metrics.json").write_text(json.dumps(result.metrics, indent=2), encoding="utf-8")
        if result.rows:
            with (cand_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as fp:
                writer = csv.DictWriter(fp, fieldnames=list(result.rows[0].keys()))
                writer.writeheader()
                writer.writerows(result.rows)

        events.write({
            "event": "candidate_evaluated",
            "round": round_idx,
            "name": cand["name"],
            "candidate_hash": h,
            "metrics": result.metrics,
        })
        _LOGGER.info(
            "round=%d name=%s precision=%.3f recall=%.3f f1=%.3f runtime=%.2fs cost/1k=%.4f",
            round_idx, cand["name"],
            float(result.metrics["precision"]),
            float(result.metrics["recall"]),
            float(result.metrics["f1"]),
            float(result.metrics["median_runtime_sec"]),
            float(result.metrics["estimated_cost_per_1k"]),
        )

    return round_results


def run_search(cfg: SearchConfig) -> Dict[str, Any]:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    events_path = cfg.out_dir / "events.jsonl"
    events_path.unlink(missing_ok=True)

    seeds = _load_seed_candidates(cfg.candidate_dir)
    proposer = _make_proposer(cfg.proposer, batch_size=6, seed=cfg.seed)

    seen: set[str] = set()
    history: List[Dict[str, Any]] = []
    state = StoppingState()
    final_top: List[Dict[str, Any]] = []

    samples = load_samples(cfg.dataset_dir)
    _LOGGER.info("Loaded %d samples (%d phish, %d benign).", len(samples),
                 sum(1 for s in samples if s.label == "phish"),
                 sum(1 for s in samples if s.label == "benign"))

    with JsonlWriter(events_path) as events:
        events.write({
            "event": "search_started",
            "config": {**cfg.__dict__, "dataset_dir": str(cfg.dataset_dir),
                       "candidate_dir": str(cfg.candidate_dir),
                       "out_dir": str(cfg.out_dir)},
            "num_samples": len(samples),
        })

        current_pool = seeds
        for round_idx in range(cfg.rounds + 1):
            _LOGGER.info("=== ROUND %d (pool size %d) ===", round_idx, len(current_pool))
            round_results = _evaluate_pool(
                current_pool, cfg, round_idx, history, seen, events, cfg.out_dir
            )
            if not round_results:
                events.write({"event": "round_empty", "round": round_idx})
                _LOGGER.warning("Round %d produced no new evaluations.", round_idx)
                break

            ranked = precision_floor_selector(round_results, cfg.precision_floor)
            frontier = pareto_frontier(round_results)
            best_recall = max(
                (r["metrics"]["recall"] for r in round_results
                 if r["metrics"]["precision"] >= cfg.precision_floor),
                default=0.0,
            )

            top_candidates = [r["candidate"] for r in ranked[: cfg.keep_top_k]]
            top_metrics = [r["metrics"] for r in ranked[: cfg.keep_top_k]]
            div_cand = diverse_candidate(round_results, cfg.precision_floor)
            failures = _aggregate_failure_buckets(round_results)

            (cfg.out_dir / f"round_{round_idx}_summary.json").write_text(
                json.dumps({
                    "round": round_idx,
                    "ranked_top_k": [
                        {"name": r["candidate"]["name"], **r["metrics"]} for r in ranked[: cfg.keep_top_k]
                    ],
                    "pareto_frontier": [
                        {"name": r["candidate"]["name"], **r["metrics"]} for r in frontier
                    ],
                    "best_recall_under_floor": best_recall,
                    "failure_buckets_aggregate": failures,
                }, indent=2),
                encoding="utf-8",
            )

            events.write({
                "event": "round_summary",
                "round": round_idx,
                "best_recall_under_floor": best_recall,
                "failure_buckets": failures,
                "num_evaluated": len(round_results),
                "num_pareto": len(frontier),
            })

            stop = evaluate_stopping(
                state,
                best_recall_this_round=best_recall,
                new_candidates_this_round=len(round_results),
                round_idx=round_idx,
                max_rounds=cfg.rounds,
            )
            if stop != StopReason.NOT_STOPPED:
                events.write({"event": "search_stopped", "reason": stop.value, "round": round_idx})
                _LOGGER.info("Stopping search: %s", stop.value)
                final_top = ranked
                break

            ctx = ProposerContext(
                round_idx=round_idx + 1,
                seen_hashes=set(seen),
                history=list(history),
                top_candidates=[deepcopy(c) for c in top_candidates],
                top_metrics=[dict(m) for m in top_metrics],
                diverse_candidate=deepcopy(div_cand) if div_cand else None,
                failure_summary=dict(failures),
                precision_floor=cfg.precision_floor,
                runtime_budget_sec=cfg.runtime_budget_sec,
                cost_budget_per_1k=cfg.cost_budget_per_1k,
            )
            proposed = proposer.propose(ctx)
            for c in proposed:
                validate(c)

            keep_carry = ranked[: cfg.keep_top_k] + (frontier[: cfg.keep_frontier_k] if frontier else [])
            keep_names = {r["candidate"]["name"] for r in keep_carry}
            current_pool = proposed + [
                deepcopy(r["candidate"]) for r in keep_carry
                if candidate_hash(r["candidate"]) not in seen and r["candidate"]["name"] in keep_names
            ]
            final_top = ranked

        events.write({"event": "search_finished", "rounds_run": min(round_idx + 1, cfg.rounds + 1)})

    if history:
        summary_path = cfg.out_dir / "search_summary.csv"
        flat = [_flatten(h) for h in history]
        with summary_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(flat[0].keys()))
            writer.writeheader()
            writer.writerows(flat)

    if final_top:
        top5 = [
            {"name": r["candidate"]["name"], "metrics": r["metrics"], "candidate": r["candidate"]}
            for r in final_top[:5]
        ]
        (cfg.out_dir / "top5.json").write_text(json.dumps(top5, indent=2), encoding="utf-8")

    return {
        "rounds_run": round_idx + 1,
        "history": history,
        "top": final_top[:5] if final_top else [],
    }


def _flatten(record: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a metrics record so it can be written as a single CSV row."""
    flat: Dict[str, Any] = {}
    for k, v in record.items():
        if k == "failure_buckets" and isinstance(v, dict):
            for bk, bv in v.items():
                flat[f"failures.{bk}"] = bv
        elif k == "confusion" and isinstance(v, dict):
            for ya, row in v.items():
                for pa, val in row.items():
                    flat[f"cm.{ya}.{pa}"] = val
        else:
            flat[k] = v
    return flat
