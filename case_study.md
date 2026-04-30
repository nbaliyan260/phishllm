# AI-Driven Configuration Search for PhishLLM-Style Phishing Detection

**Author:** Nazish Baliyan — CS7602 Coursework Case Study
**Selected paper:** Liu et al., *Less Defined Knowledge and More True Alarms: Reference-based Phishing Detection without a Pre-defined Reference List*, USENIX Security 2024

## Problem setup
PhishLLM is a four-stage reference-free phishing detector — brand recognition, credential-requiring-page (CRP) detection, optional CRP transition, and validation/fusion. Each stage exposes prompt and policy knobs that interact non-trivially. I formulate the inference-time configuration as a candidate space and use AI to search it under a hard precision floor of 0.95 and bounded runtime/cost. A candidate is a JSON object validated against a fixed schema; the evaluator is a frozen `evaluate(candidate, dataset)` returning precision, recall, F1, FPR/FNR, runtime, estimated cost per 1K pages, a confusion matrix, and a structured failure-bucket histogram.

## Solution generator
Two interchangeable proposers share the same `ProposerContext`. The **heuristic proposer** is deterministic and dependency-free; it picks among `{recall, precision, robustness, validation, cost}` mutations conditioned on the dominant failure bucket of the previous round. The **LLM proposer** calls Anthropic Claude with a meta-prompt containing the schema, top-K candidates, one diverse under-performer, and the failure summary; it parses, JSON-schema-validates, and de-duplicates the returned candidates, falling back to the heuristic proposer on any error. A precision-floor selector ranks each round by `(floor_ok, recall, F1, -runtime, -cost)`; the Pareto frontier over `(recall ↑, runtime ↓, cost ↓)` is preserved between rounds. Search stops after 4 rounds or after two rounds with <1% recall gain under the floor.

## Evaluator and metrics
The dataset uses the per-site folder layout from the official PhishLLM repository (`info.txt`, `html.txt`, optional `shot.png`) plus a `labels.csv` with ground-truth label, target brand, and CRP flag. The synthetic split contains **142 samples** (72 phishing / 70 benign) across six phishing templates (brand mismatch, typosquat, hidden-login, prompt injection, crypto, lesser-known brand) and seven benign templates including two adversarial classes (indie sites with brand-like URL stems, hosted dev projects). Recall is reported with a 95% percentile-bootstrap CI (1 000 iterations, seeded).

## Results
20 candidates across 3 rounds; 15 met the precision floor. The best candidate (`round2_thr90`) achieves **precision 1.00, recall 1.00, F1 1.00** at a median runtime of **0.55 s** and an estimated cost of **\$0.50/1K pages**, versus the official-style baseline (`seed_baseline`: P=1.00, R=0.74, F1=0.85, runtime=1.70 s, cost \$2.30/1K). That is a **+26.4 percentage-point recall gain at −1.15 s runtime and −\$1.80/1K cost** — a strict Pareto improvement on the baseline.

| Candidate | P | R | F1 | runtime | \$/1K | Floor |
|---|---:|---:|---:|---:|---:|:---:|
| `seed_baseline` | 1.00 | 0.74 | 0.85 | 1.70 s | 2.30 | ✓ |
| `seed_recall_first` | 0.78 | 1.00 | 0.88 | 1.70 s | 2.30 | ✗ |
| `seed_no_validation` | 0.51 | 0.74 | 0.60 | 1.30 s | 1.70 | ✗ |
| `seed_robust` | 1.00 | 1.00 | 1.00 | 1.70 s | 2.30 | ✓ |
| **`round2_thr90` (best)** | **1.00** | **1.00** | **1.00** | **0.55 s** | **0.50** | **✓** |

The most informative failure bucket across the search was `brand_miss` (133 events), driven by lesser-known brands. Disabling `popularity_validation` produced **50 alias false-positives** (`seed_no_validation`), confirming that the paper's validation stage is genuinely load-bearing rather than ornamental.

## Search behaviour
The search trace shows best-recall-so-far growing monotonically under the precision floor, with the largest jumps in the earliest rounds and diminishing returns thereafter — the textbook signature of a useful but finite search signal. The Pareto frontier yields three operating points that practitioners would actually pick: a low-cost no-interaction point, a balanced cached-validation point, and a high-recall robust-prompt point. The final stopping reason was `no_recall_gain_under_floor` after round 2.

## Honest scope
The evaluator backend is a transparent rule emulator over a deterministic synthetic 142-site split, not the real PhishLLM pipeline. The absolute numbers (in particular the perfect P=R=F1=1.0 of the best candidate) are therefore not directly comparable to the paper's 12K-sample benchmark. The contribution of this project is the *trade-off pattern* — popularity validation is load-bearing, robust prompts strictly dominate recall-leaning prompts on adversarial benign pages, cached validation is near-free, prompt-injection defence is near-free — and the documented `OfficialRepoBackend` adapter that lets the same search loop, evaluator, reporting, and Slurm scripts run unchanged against the upstream repository for a faithful evaluation.

## Lessons for practitioners
1. **Popularity validation is part of the contract, not an optimisation knob.** Disabling it caused the largest single harm (alias FPs jumped from 0 to 50).
2. **Recall-leaning brand prompts need a corroborating signal.** URL-stem fallback alone over-flags benign indie sites; gating it on suspicious TLD / hosting domain (the `brand_robust_v1` prompt) eliminates 100% of those FPs without losing recall.
3. **Cached popularity validation is almost free.** It cuts runtime from 1.70 s to 0.90 s and cost from \$2.30 to \$1.00 per 1K pages with no recall loss.
4. **Prompt-injection defence has near-zero cost.** `prompt_defense=true` never harmed any operating point and was load-bearing for the prompt-injection samples.
5. **Structured feedback matters for AI search.** Passing the LLM proposer the failure-bucket histogram, the top-K *and* a diverse under-performer reduced duplicate proposals dramatically compared to passing only aggregate metrics.

## Reproduction
```bash
make install            # runtime deps only (no API key required)
make demo               # dataset + baseline + 1 search round + plots
make search ROUNDS=4    # full search loop, deterministic
make report             # plots, tables, case_study.md
```
Set `ANTHROPIC_API_KEY` and run `make search PROPOSER=llm` to switch to Claude. All artifacts land in `runs/` and `artifacts/`.
