# AI-Driven Configuration Search for PhishLLM-Style Phishing Detection

**Author:** Nazish Baliyan -- CS7602 Coursework Case Study\
**Paper:** Liu et al., *Less Defined Knowledge and More True Alarms: Reference-based Phishing Detection without a Pre-defined Reference List*, USENIX Security 2024.

## Problem setup
PhishLLM is a four-stage detector (brand recognition -> CRP detection -> CRP transition -> validation+fusion).
Each stage exposes prompt and policy knobs that interact with each other in non-obvious ways.
This project formulates the *inference-time configuration* as a candidate space and asks an AI proposer to
search it, subject to a hard precision floor of 0.95 and bounded runtime/cost.
A candidate is a JSON object validated against a fixed JSON Schema; the evaluator is a frozen
`evaluate(candidate, dataset)` function that returns precision, recall, F1, FPR/FNR, runtime,
estimated cost per 1K pages, a confusion matrix, and a structured failure-bucket histogram.

## Solution generator
Two interchangeable proposers share the same `ProposerContext`:

1. **Heuristic proposer.** Deterministic, dependency-free, reproducible. Picks among
   `recall`, `precision`, `robustness`, `validation`, and `cost` mutations based on the
   dominant failure bucket of the previous round.
2. **LLM proposer.** Calls Anthropic Claude with a meta-prompt containing the schema, top-k
   candidates, one diverse under-performer, and the failure summary; parses, validates, and
   de-duplicates the JSON array it returns. Falls back to the heuristic proposer if the API
   is unavailable, so the pipeline is always runnable.

After every round a precision-floor selector ranks candidates by `(floor_ok, recall, F1, -runtime, -cost)`,
the Pareto frontier over `(recall up, runtime down, cost down)` is computed, and a stopping
test terminates the search after `max_rounds` or after two consecutive rounds with <1% recall gain.

## Evaluator and metrics
The dataset uses the per-site folder layout from the official PhishLLM repository
(`info.txt`, `html.txt`, optional `shot.png`) and a `labels.csv` with ground-truth label,
target brand, and a CRP flag. 142 samples were used for the reduced split
(72 phishing / 70 benign), spanning brand mismatch, hidden-login,
prompt injection, alias false-positive, crypto phishing, and typosquatting cases.
Recall is reported with a 95% percentile-bootstrap CI (1k iterations).

## Results
14 candidates were evaluated across 2 rounds.
11 candidates met the precision floor.
The best candidate, **round1_int0**, achieves
precision 1.000, recall 1.000, F1 1.000
at a median runtime of 0.55s and an estimated cost of
$0.5000 / 1K pages, versus the baseline candidate
**seed_baseline** (precision 1.000, recall 0.736,
F1 0.848). That is a recall improvement of
**+0.264** at **-1.15s** runtime delta and
**$-1.8000** cost delta per 1K pages.

The most informative failure bucket across the search was **brand_miss** (114
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
robust point. The final stopping reason was *max_rounds_reached*.

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
end-to-end on the deterministic heuristic proposer; setting `ANTHROPIC_API_KEY` and
`PROPOSER=llm` switches to Claude.
