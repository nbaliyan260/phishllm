"""Proposer protocol and shared context dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol


@dataclass
class ProposerContext:
    """Information passed to every proposer at the start of a round.

    Keeping this in a single dataclass means the LLM and heuristic proposers
    consume the same feedback structure, which makes them swappable from
    the CLI without touching ``loop.py``.
    """

    round_idx: int
    seen_hashes: set[str]
    history: List[Dict[str, Any]]                       # all evaluated metrics so far
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    top_metrics: List[Dict[str, Any]] = field(default_factory=list)
    diverse_candidate: Dict[str, Any] | None = None
    failure_summary: Dict[str, int] = field(default_factory=dict)
    precision_floor: float = 0.95
    runtime_budget_sec: float = 6.0
    cost_budget_per_1k: float = 5.0


class Proposer(Protocol):
    """Anything that can produce a fresh batch of candidate configs."""

    def propose(self, ctx: ProposerContext) -> List[Dict[str, Any]]:  # pragma: no cover - protocol
        ...
