"""Pluggable candidate proposers.

The exported :class:`LLMProposer` is the unified multi-provider proposer
defined in :mod:`phishllm_search.search.proposers.llm_proposer` (Anthropic
Claude, Google Gemini, or deterministic heuristic fallback).
"""

from .base import Proposer, ProposerContext
from .heuristic import HeuristicProposer
from .llm_proposer import LLMCostTracker, LLMProposer

__all__ = [
    "Proposer",
    "ProposerContext",
    "HeuristicProposer",
    "LLMProposer",
    "LLMCostTracker",
]
