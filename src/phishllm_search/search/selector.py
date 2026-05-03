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


def dominates(a: Dict, b: Dict) -> bool:
    """Return True iff metrics ``a`` dominate metrics ``b``.

    Dominance is defined over (recall up, runtime down, cost down):
    ``a`` dominates ``b`` iff ``a`` is no worse on every axis **and**
    strictly better on at least one axis. Ties on every axis are *not*
    dominance.

    Accepts either the metrics dict directly or a record of the shape
    ``{"candidate": ..., "metrics": {...}}``.
    """
    ma = a.get("metrics", a)
    mb = b.get("metrics", b)
    r_a, r_b = float(ma.get("recall", 0.0)), float(mb.get("recall", 0.0))
    t_a, t_b = float(ma.get("median_runtime_sec", 0.0)), float(mb.get("median_runtime_sec", 0.0))
    c_a, c_b = float(ma.get("estimated_cost_per_1k", 0.0)), float(mb.get("estimated_cost_per_1k", 0.0))
    no_worse = (r_a >= r_b) and (t_a <= t_b) and (c_a <= c_b)
    strictly_better = (r_a > r_b) or (t_a < t_b) or (c_a < c_b)
    return no_worse and strictly_better


def select_carry_candidates(
    evaluated: List[Dict],
    precision_floor: float = 0.95,
    *,
    max_frontier: int = 2,
) -> List[Dict]:
    """Spec-compliant carry-over selection for the next search round.

    Rules (in order):

    1. Discard all candidates with ``precision < precision_floor``.
    2. Keep the best-recall candidate.
    3. Keep up to ``max_frontier`` additional Pareto-frontier candidates.
    4. Keep the single lowest-cost candidate (ties broken by best recall).

    Results are de-duplicated by candidate ``name`` so the same record is
    never carried over twice. ``evaluated`` is not modified.
    """
    keepers: List[Dict] = []
    seen_names: set[str] = set()

    def _push(record: Dict) -> None:
        name = record.get("candidate", {}).get("name")
        if not name or name in seen_names:
            return
        seen_names.add(name)
        keepers.append(record)

    above_floor = [
        r for r in evaluated
        if float(r.get("metrics", {}).get("precision", 0.0)) >= precision_floor
    ]
    if not above_floor:
        return []

    best_recall = max(
        above_floor,
        key=lambda r: (
            float(r["metrics"].get("recall", 0.0)),
            float(r["metrics"].get("f1", 0.0)),
            -float(r["metrics"].get("median_runtime_sec", 0.0)),
            -float(r["metrics"].get("estimated_cost_per_1k", 0.0)),
        ),
    )
    _push(best_recall)

    for record in pareto_frontier(above_floor):
        if len([k for k in keepers if k is not best_recall]) >= max_frontier:
            break
        _push(record)

    if above_floor:
        lowest_cost = min(
            above_floor,
            key=lambda r: (
                float(r["metrics"].get("estimated_cost_per_1k", 0.0)),
                -float(r["metrics"].get("recall", 0.0)),
            ),
        )
        _push(lowest_cost)

    return keepers
