"""LLM-driven proposer (Anthropic Claude).

Calls the Anthropic Messages API with a structured meta-prompt built from the
current evaluation feedback. Falls back to the :class:`HeuristicProposer`
when the SDK or API key is unavailable, so the search loop is always
runnable.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...schema import schema_summary, validate_many
from ...utils.hashing import candidate_hash
from ...utils.logging import get_logger
from .base import ProposerContext
from .heuristic import HeuristicProposer


_LOGGER = get_logger("proposer.llm")
_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "prompts" / "meta_search_prompt.txt"
)


@dataclass
class LLMProposerConfig:
    """User-tunable knobs for the LLM proposer."""

    model: str = "claude-3-5-sonnet-latest"
    max_tokens: int = 1500
    temperature: float = 0.4
    batch_size: int = 5
    fallback_seed: int = 0
    api_key_env: str = "ANTHROPIC_API_KEY"


class LLMProposer:
    """Use Claude to draft new candidates; fall back to heuristics on failure."""

    def __init__(self, config: Optional[LLMProposerConfig] = None) -> None:
        self.config = config or LLMProposerConfig()
        self._fallback = HeuristicProposer(batch_size=self.config.batch_size,
                                            seed=self.config.fallback_seed)
        self._client = self._init_client()
        self._template = _PROMPT_PATH.read_text(encoding="utf-8")

    def _init_client(self):
        api_key = os.getenv(self.config.api_key_env, "").strip()
        if not api_key:
            _LOGGER.info("No %s set; LLM proposer will fall back to heuristic.", self.config.api_key_env)
            return None
        try:
            import anthropic  # type: ignore
        except ImportError:
            _LOGGER.warning("anthropic package not installed; LLM proposer will fall back to heuristic.")
            return None
        try:
            return anthropic.Anthropic(api_key=api_key)
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.warning("Could not initialise Anthropic client: %s; falling back.", exc)
            return None

    def propose(self, ctx: ProposerContext) -> List[Dict[str, Any]]:
        if self._client is None:
            return self._fallback.propose(ctx)

        prompt = self._render_prompt(ctx)
        try:
            response = self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            _LOGGER.warning("LLM call failed (%s); falling back to heuristic proposer.", exc)
            return self._fallback.propose(ctx)

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        candidates = _parse_json_array(text)
        if not candidates:
            _LOGGER.warning("LLM returned no parsable JSON array; falling back to heuristic.")
            return self._fallback.propose(ctx)

        for c in candidates:
            c["backend"] = ctx.top_candidates[0].get("backend", "mock") if ctx.top_candidates else "mock"
            c.setdefault("temperature", 0.0)
            c.setdefault("runtime_budget_sec", float(ctx.runtime_budget_sec))

        valid, errors = validate_many(candidates)
        if errors:
            _LOGGER.warning("LLM produced %d invalid candidates (kept %d). First error: %s",
                            len(errors), len(valid), errors[0])

        unique: List[Dict[str, Any]] = []
        seen_local: set[str] = set()
        for cand in valid:
            h = candidate_hash(cand)
            if h in ctx.seen_hashes or h in seen_local:
                continue
            seen_local.add(h)
            unique.append(cand)
            if len(unique) >= self.config.batch_size:
                break

        if not unique:
            _LOGGER.warning("All LLM proposals were duplicates or invalid; falling back to heuristic.")
            return self._fallback.propose(ctx)
        return unique

    def _render_prompt(self, ctx: ProposerContext) -> str:
        top_block = json.dumps(
            [{"candidate": c, "metrics": m} for c, m in zip(ctx.top_candidates, ctx.top_metrics)],
            indent=2,
        )
        diverse_block = json.dumps(ctx.diverse_candidate or {}, indent=2)
        failure_block = json.dumps(ctx.failure_summary, indent=2)
        fixed_backend = ctx.top_candidates[0].get("backend", "mock") if ctx.top_candidates else "mock"
        return self._template.format(
            schema_summary=schema_summary(),
            fixed_backend=fixed_backend,
            round_idx=ctx.round_idx,
            precision_floor=ctx.precision_floor,
            runtime_budget_sec=ctx.runtime_budget_sec,
            cost_budget=ctx.cost_budget_per_1k,
            top_candidates_block=top_block,
            diverse_candidate_block=diverse_block,
            failure_summary_block=failure_block,
        )


def _parse_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array of candidate objects from ``text``.

    Tolerates optional markdown fences and surrounding prose, since LLMs
    sometimes ignore the "no markdown" instruction.
    """
    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if fence:
        blob = fence.group(1)
    else:
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return []
        blob = m.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list) and all(isinstance(d, dict) for d in data):
        return [deepcopy(d) for d in data]
    return []
