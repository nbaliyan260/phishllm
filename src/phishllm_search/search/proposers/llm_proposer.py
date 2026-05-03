"""Unified multi-provider LLM proposer.

Supports three modes controlled by the ``mode`` argument (or the ``auto``
heuristic over environment variables):

* ``"anthropic"`` -- Claude via the ``anthropic`` SDK.
* ``"gemini"``    -- Gemini via the ``google-generativeai`` SDK.
* ``"heuristic"`` -- deterministic mutation fallback (no network).
* ``"auto"``      -- pick the first provider whose API key is set, else
  fall back transparently to the heuristic proposer.

Any failure at any stage (missing SDK, missing key, HTTP error, malformed
JSON, schema-invalid candidate, all-duplicates, etc.) is caught and the
heuristic fallback is used instead, so the search loop is **always**
runnable even offline. This matches the course-brief constraint that the
pipeline works with no API keys set.

The proposer builds the structured JSON meta-prompt described in the
project spec (``objective`` / ``hard_constraints`` / ``candidate_schema``
/ ``top_candidates`` / ``diverse_underperformer`` / ``failure_summary``
/ ``instructions``) and asks the LLM to return a JSON array of schema-valid
candidates. Token usage is recorded per call; a best-effort cost estimate
per provider is exposed via :class:`LLMCostTracker`.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from ...schema import schema as load_candidate_schema, validate_many
from ...utils.hashing import candidate_hash
from ...utils.logging import get_logger
from .base import ProposerContext
from .heuristic import HeuristicProposer

_LOGGER = get_logger("proposer.llm_unified")

Mode = Literal["auto", "anthropic", "gemini", "heuristic"]


# ---- cost tracking ---------------------------------------------------------

# Token prices (USD) per 1K tokens. These are coarse, public list-price
# estimates at the time of writing and are intended for *relative* cost
# reasoning in the search report, not for billing accuracy.
_ANTHROPIC_INPUT_PER_1K = 0.00025   # claude-3-haiku-20240307 input
_ANTHROPIC_OUTPUT_PER_1K = 0.00075  # claude-3-haiku-20240307 output
_GEMINI_PER_1K = 0.00035            # gemini-1.5-flash combined approx


@dataclass
class LLMCostTracker:
    """Cumulative token + dollar usage for LLM proposer calls."""

    total_calls: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    estimated_cost_usd: float = 0.0
    per_provider_calls: Dict[str, int] = field(default_factory=dict)

    def record(self, provider: str, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self.total_calls += 1
        self.tokens_input += int(tokens_in)
        self.tokens_output += int(tokens_out)
        self.estimated_cost_usd = round(self.estimated_cost_usd + float(cost_usd), 6)
        self.per_provider_calls[provider] = self.per_provider_calls.get(provider, 0) + 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "per_provider_calls": dict(self.per_provider_calls),
        }


# ---- main proposer --------------------------------------------------------


class LLMProposer:
    """Provider-agnostic LLM proposer with deterministic heuristic fallback.

    The constructor never raises: if the selected provider is unavailable
    (missing SDK, missing API key) the instance silently degrades to the
    heuristic fallback so :meth:`propose` still returns a valid batch.
    """

    _ANTHROPIC_MODEL = "claude-3-haiku-20240307"
    _GEMINI_MODEL = "gemini-1.5-flash"
    _MAX_TOKENS = 2000
    _TEMPERATURE = 0.0
    _SYSTEM_PROMPT = (
        "You are a configuration search assistant for phishing detection. "
        "Return ONLY a JSON array of candidate objects -- no prose, no markdown."
    )

    def __init__(
        self,
        mode: Mode = "auto",
        *,
        batch_size: int = 6,
        fallback_seed: int = 0,
        anthropic_key_env: str = "ANTHROPIC_API_KEY",
        gemini_key_env: str = "GEMINI_API_KEY",
    ) -> None:
        self.requested_mode: Mode = mode
        self.batch_size = int(batch_size)
        self._heuristic = HeuristicProposer(batch_size=batch_size, seed=fallback_seed)
        self._anthropic_key_env = anthropic_key_env
        self._gemini_key_env = gemini_key_env
        self.cost_tracker = LLMCostTracker()

        self._provider: str = "heuristic"
        self._anthropic_client = None
        self._gemini_model = None
        self._resolve_provider(mode)

    # ---- provider resolution ----------------------------------------------

    def _resolve_provider(self, mode: Mode) -> None:
        if mode == "heuristic":
            self._provider = "heuristic"
            return

        if mode == "anthropic":
            if self._try_init_anthropic():
                self._provider = "anthropic"
            else:
                _LOGGER.warning("Anthropic requested but unavailable; falling back to heuristic.")
                self._provider = "heuristic"
            return

        if mode == "gemini":
            if self._try_init_gemini():
                self._provider = "gemini"
            else:
                _LOGGER.warning("Gemini requested but unavailable; falling back to heuristic.")
                self._provider = "heuristic"
            return

        if self._try_init_anthropic():
            self._provider = "anthropic"
        elif self._try_init_gemini():
            self._provider = "gemini"
        else:
            _LOGGER.info("No LLM provider keys detected; using deterministic heuristic proposer.")
            self._provider = "heuristic"

    def _try_init_anthropic(self) -> bool:
        key = os.getenv(self._anthropic_key_env, "").strip()
        if not key:
            return False
        try:
            import anthropic  # type: ignore
        except ImportError:
            _LOGGER.warning("anthropic SDK not installed; cannot use Anthropic provider.")
            return False
        try:
            self._anthropic_client = anthropic.Anthropic(api_key=key)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.warning("Failed to initialise Anthropic client: %s", exc)
            return False

    def _try_init_gemini(self) -> bool:
        key = os.getenv(self._gemini_key_env, "").strip()
        if not key:
            return False
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            _LOGGER.warning("google-generativeai SDK not installed; cannot use Gemini provider.")
            return False
        try:
            genai.configure(api_key=key)
            self._gemini_model = genai.GenerativeModel(
                self._GEMINI_MODEL,
                system_instruction=self._SYSTEM_PROMPT,
            )
            return True
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.warning("Failed to initialise Gemini client: %s", exc)
            return False

    @property
    def provider(self) -> str:
        """Resolved provider string: 'anthropic' | 'gemini' | 'heuristic'."""
        return self._provider

    # ---- main API ---------------------------------------------------------

    def propose(self, ctx: ProposerContext) -> List[Dict[str, Any]]:
        if self._provider == "heuristic":
            return self._heuristic.propose(ctx)

        try:
            meta_prompt = self._build_meta_prompt(ctx)
        except Exception as exc:
            _LOGGER.warning("Failed to build meta prompt (%s); falling back to heuristic.", exc)
            return self._heuristic.propose(ctx)

        try:
            if self._provider == "anthropic":
                raw_text = self._call_anthropic(meta_prompt)
            else:
                raw_text = self._call_gemini(meta_prompt)
        except Exception as exc:
            _LOGGER.warning("%s call failed (%s); falling back to heuristic.", self._provider, exc)
            return self._heuristic.propose(ctx)

        try:
            candidates = _extract_json_array(raw_text)
        except Exception as exc:
            _LOGGER.warning("JSON extraction failed (%s); falling back to heuristic.", exc)
            return self._heuristic.propose(ctx)

        if not candidates:
            _LOGGER.warning("%s returned no parsable candidates; falling back to heuristic.",
                            self._provider)
            return self._heuristic.propose(ctx)

        sanitized = self._sanitize_candidates(candidates, ctx)
        valid, errors = validate_many(sanitized)
        if errors:
            _LOGGER.warning(
                "%d/%d LLM candidates failed schema validation; first error: %s",
                len(errors), len(sanitized), errors[0],
            )

        unique = self._dedupe(valid, ctx)
        if not unique:
            _LOGGER.warning(
                "All %s proposals were duplicates or invalid; falling back to heuristic.",
                self._provider,
            )
            return self._heuristic.propose(ctx)
        return unique

    # ---- providers --------------------------------------------------------

    def _call_anthropic(self, meta_prompt: Dict[str, Any]) -> str:
        assert self._anthropic_client is not None
        message = self._anthropic_client.messages.create(
            model=self._ANTHROPIC_MODEL,
            max_tokens=self._MAX_TOKENS,
            temperature=self._TEMPERATURE,
            system=self._SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(meta_prompt, indent=2)}],
        )

        tokens_in = int(getattr(message.usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(message.usage, "output_tokens", 0) or 0)
        cost = (
            tokens_in / 1000.0 * _ANTHROPIC_INPUT_PER_1K
            + tokens_out / 1000.0 * _ANTHROPIC_OUTPUT_PER_1K
        )
        self.cost_tracker.record("anthropic", tokens_in, tokens_out, cost)

        return "".join(
            block.text for block in message.content
            if getattr(block, "type", "") == "text"
        )

    def _call_gemini(self, meta_prompt: Dict[str, Any]) -> str:
        assert self._gemini_model is not None
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:  # pragma: no cover
            raise RuntimeError("google-generativeai not importable at call time")

        response = self._gemini_model.generate_content(
            json.dumps(meta_prompt, indent=2),
            generation_config=genai.types.GenerationConfig(
                temperature=self._TEMPERATURE,
                top_p=0.95,
                max_output_tokens=self._MAX_TOKENS,
            ),
        )

        usage = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
        cost = (tokens_in + tokens_out) / 1000.0 * _GEMINI_PER_1K
        self.cost_tracker.record("gemini", tokens_in, tokens_out, cost)

        if hasattr(response, "text") and response.text:
            return str(response.text)
        texts: List[str] = []
        for cand in getattr(response, "candidates", []) or []:
            for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                txt = getattr(part, "text", None)
                if txt:
                    texts.append(str(txt))
        return "".join(texts)

    # ---- meta prompt ------------------------------------------------------

    def _build_meta_prompt(self, ctx: ProposerContext) -> Dict[str, Any]:
        top_candidates = [
            {"candidate": c, "metrics": m}
            for c, m in zip(ctx.top_candidates, ctx.top_metrics)
        ]
        diverse = ctx.diverse_candidate or {}
        fixed_backend = (
            ctx.top_candidates[0].get("backend", "mock") if ctx.top_candidates else "mock"
        )
        return {
            "objective": "Maximize recall under precision >= {:.2f}".format(
                ctx.precision_floor
            ),
            "hard_constraints": {
                "precision_floor": ctx.precision_floor,
                "runtime_budget_sec": ctx.runtime_budget_sec,
                "cost_budget_per_1k": ctx.cost_budget_per_1k,
                "fixed_backend": fixed_backend,
            },
            "candidate_schema": load_candidate_schema(),
            "top_candidates": top_candidates,
            "diverse_underperformer": diverse,
            "failure_summary": {
                "false_negatives": [],
                "false_positives": [],
                "failure_buckets": dict(ctx.failure_summary),
            },
            "round_idx": ctx.round_idx,
            "instructions": [
                "Propose 4-6 schema-valid candidates.",
                "Do not add new fields beyond the schema's allowed properties.",
                "Each candidate MUST include a unique 'name' starting with "
                "'round{}_'".format(ctx.round_idx) + ".",
                "Each candidate MUST include a one-sentence 'hypothesis' field.",
                "Focus on recall improvements without violating the precision constraint.",
                "Do not modify 'backend'; keep it as '{}'".format(fixed_backend) + ".",
                "Do not propose duplicates of already-evaluated candidates.",
                "Return ONLY a JSON array. No markdown fences, no prose.",
            ],
        }

    # ---- sanitation / dedup ----------------------------------------------

    def _sanitize_candidates(
        self,
        candidates: List[Dict[str, Any]],
        ctx: ProposerContext,
    ) -> List[Dict[str, Any]]:
        fixed_backend = (
            ctx.top_candidates[0].get("backend", "mock") if ctx.top_candidates else "mock"
        )
        out: List[Dict[str, Any]] = []
        for i, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                continue
            c = deepcopy(cand)
            c["backend"] = fixed_backend
            c.setdefault("temperature", 0.0)
            c.setdefault("runtime_budget_sec", float(ctx.runtime_budget_sec))
            name = str(c.get("name", "")).strip()
            if not name:
                name = f"round{ctx.round_idx}_llm_{i}"
            if not name.startswith(f"round{ctx.round_idx}_"):
                name = f"round{ctx.round_idx}_llm_{name}"
            c["name"] = name[:80]
            out.append(c)
        return out

    def _dedupe(
        self,
        candidates: List[Dict[str, Any]],
        ctx: ProposerContext,
    ) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        seen_local: set[str] = set()
        for cand in candidates:
            h = candidate_hash(cand)
            if h in ctx.seen_hashes or h in seen_local:
                continue
            seen_local.add(h)
            unique.append(cand)
            if len(unique) >= self.batch_size:
                break
        return unique


# ---- helpers --------------------------------------------------------------


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array of objects from ``text``.

    Strategy (most forgiving first):
    1. Look for a fenced ```json ... ``` block.
    2. Otherwise take the substring between the first '[' and the last ']'.
    Return [] on any parse failure; callers must handle the empty case.
    """
    if not text:
        return []

    fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if fence:
        blob = fence.group(1)
    else:
        first = text.find("[")
        last = text.rfind("]")
        if first == -1 or last == -1 or last <= first:
            return []
        blob = text[first : last + 1]

    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []
    return [deepcopy(item) for item in data if isinstance(item, dict)]


__all__ = ["LLMProposer", "LLMCostTracker", "Mode"]
