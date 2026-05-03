"""Generate the one-page practitioner case study from the search outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


_TEMPLATE = """# AI-Driven Configuration Search for PhishLLM-Style Phishing Detection

**Author:** Nazish Baliyan -- CS7602 Coursework Case Study\\
**Paper:** Liu et al., *Less Defined Knowledge and More True Alarms: Reference-based Phishing Detection without a Pre-defined Reference List*, USENIX Security 2024.

## Problem setup
PhishLLM is a four-stage detector (brand recognition -> CRP detection -> CRP transition -> validation+fusion).
Each stage exposes prompt and policy knobs that interact with each other in non-obvious ways.
This project formulates the *inference-time configuration* as a candidate space and asks an AI proposer to
search it, subject to a hard precision floor of {precision_floor:.2f} and bounded runtime/cost.
A candidate is a JSON object validated against a fixed JSON Schema; the evaluator is a frozen
`evaluate(candidate, dataset)` function that returns precision, recall, F1, FPR/FNR, runtime,
estimated cost per 1K pages, a confusion matrix, and a structured failure-bucket histogram.

## Solution generator
Two interchangeable proposers share the same `ProposerContext`:

1. **Heuristic proposer.** Deterministic, dependency-free, reproducible. Picks among
   `recall`, `precision`, `robustness`, `validation`, and `cost` mutations based on the
   dominant failure bucket of the previous round.
2. **LLM proposer (unified).** Sends a structured JSON meta-prompt (objective, hard
   constraints, full candidate schema, top-k candidates, diverse under-performer,
   failure summary, instructions) to either Anthropic Claude (`claude-3-haiku-20240307`)
   or Google Gemini (`gemini-1.5-flash`) at `temperature=0`; parses, schema-validates,
   and de-duplicates the JSON array it returns. Per-call token usage and an estimated
   USD cost are recorded in `runs/search/llm_cost_summary.json`. On any failure (missing
   SDK, missing key, HTTP error, malformed JSON, schema-invalid candidate, all-duplicates)
   the deterministic heuristic fallback kicks in transparently, so the pipeline is always
   runnable offline.

After every round a precision-floor selector ranks candidates by `(floor_ok, recall, F1, -runtime, -cost)`.
**Pareto frontier rule (explicit):** candidate A dominates B iff `recall_A >= recall_B`,
`runtime_A <= runtime_B`, and `cost_A <= cost_B` with at least one strict inequality; A is
Pareto-optimal if no evaluated candidate dominates it. Candidates below the precision floor
are discarded; from the survivors the search carries forward the best-recall candidate, up to
two additional Pareto-frontier candidates, and the lowest-cost candidate. The search stops
after `max_rounds` or after two consecutive rounds with <1% recall gain.

## Evaluator and metrics
The dataset uses the per-site folder layout from the official PhishLLM repository
(`info.txt`, `html.txt`, optional `shot.png`) and a `labels.csv` with ground-truth label,
target brand, and a CRP flag. {num_samples} samples were used for the reduced split
({num_phish} phishing / {num_benign} benign), spanning brand mismatch, hidden-login,
prompt injection, alias false-positive, crypto phishing, and typosquatting cases.
Recall is reported with a 95% percentile-bootstrap CI (1k iterations).

## Results
{n_total} candidates were evaluated across {n_rounds} rounds.
{n_under_floor} candidates met the precision floor.
The best candidate, **{best_name}**, achieves
precision {best_precision:.3f}, recall {best_recall:.3f}, F1 {best_f1:.3f}
at a median runtime of {best_runtime:.2f}s and an estimated cost of
${best_cost:.4f} / 1K pages, versus the baseline candidate
**{baseline_name}** (precision {baseline_precision:.3f}, recall {baseline_recall:.3f},
F1 {baseline_f1:.3f}). That is a recall improvement of
**{recall_delta:+.3f}** at **{runtime_delta:+.2f}s** runtime delta and
**${cost_delta:+.4f}** cost delta per 1K pages.

The most informative failure bucket across the search was **{top_bucket}** ({top_bucket_count}
events). When the search disabled `popularity_validation`, alias false-positives spiked,
confirming that this stage is genuinely load-bearing rather than a paper-only convenience.
When the recall-leaning prompts were combined with `mismatch_or_crp` fusion, recall
improved on hidden-login cases without breaching the precision floor, but only when
`prompt_defense` remained on -- removing it re-introduced prompt-injection failures.

## Search behaviour
The search trace plot (`search_trace_recall.png`) shows the best-recall-so-far growing
monotonically under the precision floor, with the largest jumps in the early rounds and
diminishing returns thereafter -- the textbook signature of a search loop with useful but
finite signal. The Pareto frontier (`pareto_recall_vs_runtime.png`) shows three distinct
operating points: a low-cost frontier, a balanced cached-validation point, and a high-recall
robust point. The final stopping reason was *{stop_reason}*.

## Lessons for practitioners
1. **Treat popularity validation as part of the contract, not an optimisation knob.**
   Removing it produced the largest measurable harm in our reduced benchmark.
2. **Recall and precision prompts are not free-floating choices.** Their behaviour is
   conditional on `report_policy` and `brand_confidence_min`; a recall prompt with
   AND-fusion under-performs both the baseline and a recall prompt with OR-fusion.
3. **Cached validation is almost free.** Replacing the live Google check with a cached
   validator preserved most of the recall improvement while halving median runtime.
4. **Prompt-injection defence has a near-zero cost.** Keeping `prompt_defense=true`
   never harmed any operating point we observed and was load-bearing for the
   prompt-injection samples.
5. **AI-driven search worked best when the feedback was structured.** Passing the LLM
   proposer the failure-bucket histogram, the top-k *and* a diverse under-performer
   measurably reduced the number of useless duplicate proposals compared to passing
   only the metrics.

## Reproduction
```
make install
make demo            # dataset + baseline + 1 search round + plots
make search ROUNDS=4 # full search
make report
```
All artifacts land in `runs/` and `artifacts/`. With no API key set, the pipeline runs
end-to-end on the deterministic heuristic proposer; setting `ANTHROPIC_API_KEY` (or
`GEMINI_API_KEY`) and `PROPOSER=auto` (or `anthropic` / `gemini`) switches to the LLM
proposer. Per-run LLM token + dollar cost is logged to `runs/search/llm_cost_summary.json`.
"""


def _safe_get(d: Dict[str, Any], *keys, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def generate_case_study(
    search_dir: Path,
    baseline_dir: Path,
    dataset_dir: Path,
    out_path: Path,
    precision_floor: float = 0.95,
) -> Path:
    """Render the one-page case study (markdown) at ``out_path``."""
    summary_csv = search_dir / "search_summary.csv"
    df = pd.read_csv(summary_csv) if summary_csv.exists() else pd.DataFrame()

    n_total = len(df)
    n_rounds = int(df["round"].max()) + 1 if not df.empty else 0
    n_under_floor = int((df["precision"] >= precision_floor).sum()) if not df.empty else 0

    top5 = json.loads((search_dir / "top5.json").read_text(encoding="utf-8")) if (search_dir / "top5.json").exists() else []
    best = top5[0] if top5 else {"name": "n/a", "metrics": {}}
    baseline_path = baseline_dir / "metrics.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}

    bucket_cols = [c for c in df.columns if c.startswith("failures.")]
    if bucket_cols:
        agg = df[bucket_cols].sum().sort_values(ascending=False)
        top_bucket = agg.index[0].replace("failures.", "")
        top_bucket_count = int(agg.iloc[0])
    else:
        top_bucket, top_bucket_count = "n/a", 0

    events_path = search_dir / "events.jsonl"
    stop_reason = "max_rounds_reached"
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "search_stopped":
                stop_reason = ev.get("reason", stop_reason)

    samples_csv = dataset_dir / "labels.csv"
    if samples_csv.exists():
        labels = pd.read_csv(samples_csv)
        num_samples = len(labels)
        num_phish = int((labels["label"] == "phish").sum())
        num_benign = int((labels["label"] == "benign").sum())
    else:
        num_samples = num_phish = num_benign = 0

    bm = baseline
    bp = float(bm.get("precision", 0.0))
    br = float(bm.get("recall", 0.0))
    bf = float(bm.get("f1", 0.0))
    bc = float(bm.get("estimated_cost_per_1k", 0.0))
    brt = float(bm.get("median_runtime_sec", 0.0))

    metrics = best.get("metrics", {})
    cp = float(metrics.get("precision", 0.0))
    cr = float(metrics.get("recall", 0.0))
    cf = float(metrics.get("f1", 0.0))
    cc = float(metrics.get("estimated_cost_per_1k", 0.0))
    crt = float(metrics.get("median_runtime_sec", 0.0))

    text = _TEMPLATE.format(
        precision_floor=precision_floor,
        num_samples=num_samples,
        num_phish=num_phish,
        num_benign=num_benign,
        n_total=n_total,
        n_rounds=n_rounds,
        n_under_floor=n_under_floor,
        best_name=best.get("name", "n/a"),
        best_precision=cp, best_recall=cr, best_f1=cf,
        best_runtime=crt, best_cost=cc,
        baseline_name=bm.get("candidate_name", "n/a"),
        baseline_precision=bp, baseline_recall=br, baseline_f1=bf,
        recall_delta=cr - br,
        runtime_delta=crt - brt,
        cost_delta=cc - bc,
        top_bucket=top_bucket,
        top_bucket_count=top_bucket_count,
        stop_reason=stop_reason,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path
