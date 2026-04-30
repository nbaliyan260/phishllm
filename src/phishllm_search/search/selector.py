"""Selection rules: precision floor, ranking, and Pareto frontier."""

from __future__ import annotations

from typing import Dict, List, Tuple


def _score_key(metrics: Dict, precision_floor: float = 0.95) -> Tuple:
    """Lexicographic ranking used by the search loop.

    Order is: (precision-floor satisfied, recall, F1, -runtime, -cost).
    """
    precision_ok = float(metrics.get("precision", 0.0)) >= precision_floor
    return (
        1 if precision_ok else 0,
        float(metrics.get("recall", 0.0)),
        float(metrics.get("f1", 0.0)),
        -float(metrics.get("median_runtime_sec", 0.0)),
        -float(metrics.get("estimated_cost_per_1k", 0.0)),
    )


def precision_floor_selector(
    evaluated: List[Dict],
    precision_floor: float = 0.95,
) -> List[Dict]:
    """Return ``evaluated`` ordered best-first, with floor-violators last.

    Each input dict must have a ``metrics`` and ``candidate`` key.
    """
    return sorted(evaluated, key=lambda r: _score_key(r["metrics"], precision_floor), reverse=True)


def pareto_frontier(evaluated: List[Dict]) -> List[Dict]:
    """Return the Pareto-optimal subset over (recall up, runtime down, cost down).

    A point is Pareto-optimal if no other point dominates it on all three
    axes (with at least one strict improvement).
    """
    points: List[Tuple[float, float, float, Dict]] = [
        (
            float(r["metrics"].get("recall", 0.0)),
            float(r["metrics"].get("median_runtime_sec", 0.0)),
            float(r["metrics"].get("estimated_cost_per_1k", 0.0)),
            r,
        )
        for r in evaluated
    ]
    frontier: List[Dict] = []
    for i, (r_i, t_i, c_i, rec_i) in enumerate(points):
        dominated = False
        for j, (r_j, t_j, c_j, _) in enumerate(points):
            if i == j:
                continue
            better_or_eq = (r_j >= r_i) and (t_j <= t_i) and (c_j <= c_i)
            strict = (r_j > r_i) or (t_j < t_i) or (c_j < c_i)
            if better_or_eq and strict:
                dominated = True
                break
        if not dominated:
            frontier.append(rec_i)
    return frontier


def diverse_candidate(evaluated: List[Dict], precision_floor: float = 0.95) -> Dict | None:
    """Pick the lowest-scoring candidate that still produced a usable signal.

    Used by the proposer to nudge the search out of local minima.
    """
    sorted_results = sorted(evaluated, key=lambda r: _score_key(r["metrics"], precision_floor))
    for record in sorted_results:
        if record["metrics"].get("num_samples", 0) > 0:
            return record["candidate"]
    return None
