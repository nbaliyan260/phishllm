"""Search loop: propose -> evaluate -> select -> stop."""

from .loop import SearchConfig, run_search
from .selector import precision_floor_selector, pareto_frontier
from .stopping import StopReason, evaluate_stopping
from .proposers.base import Proposer, ProposerContext
from .proposers.heuristic import HeuristicProposer
from .proposers.llm_proposer import LLMCostTracker, LLMProposer

__all__ = [
    "SearchConfig",
    "run_search",
    "precision_floor_selector",
    "pareto_frontier",
    "StopReason",
    "evaluate_stopping",
    "Proposer",
    "ProposerContext",
    "HeuristicProposer",
    "LLMProposer",
    "LLMCostTracker",
]
