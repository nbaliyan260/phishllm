"""Stopping criteria for the search loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class StopReason(str, Enum):
    NOT_STOPPED = "not_stopped"
    MAX_ROUNDS = "max_rounds_reached"
    NO_RECALL_GAIN = "no_recall_gain_under_floor"
    NO_NEW_CANDIDATES = "no_new_candidates_proposed"


@dataclass
class StoppingState:
    best_recall_under_floor: float = 0.0
    rounds_without_gain: int = 0


def evaluate_stopping(
    state: StoppingState,
    best_recall_this_round: float,
    new_candidates_this_round: int,
    round_idx: int,
    max_rounds: int,
    epsilon: float = 0.01,
    patience: int = 2,
) -> StopReason:
    """Update ``state`` in place and return the stop reason for this round."""
    if new_candidates_this_round == 0 and round_idx > 0:
        return StopReason.NO_NEW_CANDIDATES

    if best_recall_this_round - state.best_recall_under_floor >= epsilon:
        state.best_recall_under_floor = best_recall_this_round
        state.rounds_without_gain = 0
    else:
        state.rounds_without_gain += 1

    if state.rounds_without_gain >= patience:
        return StopReason.NO_RECALL_GAIN

    if round_idx >= max_rounds:
        return StopReason.MAX_ROUNDS

    return StopReason.NOT_STOPPED
