# Complete project reference — PhishLLM-Search (CS7602 final)

**Author:** Nazish Baliyan  
**Purpose:** One document that records *everything* about this repository: the base paper, course fit, what is unique here, full folder layout, every file’s role, algorithms, metrics, and how to run or extend the work.

**Companion docs:** `README.md` (quick start), `case_study.md` / `case_study.tex` (one-page submission), `docs/` (architecture, failures, official-repo hookup, LaTeX appendix).

---

## Table of contents

1. [Base paper (PhishLLM)](#1-base-paper-phishllm)  
2. [Course context (CS7602 / CS8602 case study)](#2-course-context-cs7602--cs8602-case-study)  
3. [What this repository is — and what it is not](#3-what-this-repository-is--and-what-it-is-not)  
4. [What is different or “your contribution” in this project](#4-what-is-different-or-your-contribution-in-this-project)  
5. [High-level architecture](#5-high-level-architecture)  
6. [Complete folder structure](#6-complete-folder-structure)  
7. [Every tracked file — purpose](#7-every-tracked-file--purpose)  
8. [Source code — module by module](#8-source-code--module-by-module)  
9. [Candidate JSON schema](#9-candidate-json-schema)  
10. [Seed candidates (configs)](#10-seed-candidates-configs)  
11. [Prompt templates](#11-prompt-templates)  
12. [Synthetic dataset (`genset`)](#12-synthetic-dataset-genset)  
13. [Evaluator contract](#13-evaluator-contract)  
14. [Failure buckets](#14-failure-buckets)  
15. [Search loop](#15-search-loop)  
16. [Backends](#16-backends)  
17. [Reporting](#17-reporting)  
18. [Commands, Makefile, reproducibility](#18-commands-makefile-reproducibility)  
19. [Tests](#19-tests)  
20. [Slurm / HPC](#20-slurm--hpc)  
21. [Generated outputs (not always in git)](#21-generated-outputs-not-always-in-git)  
22. [Honest limitations](#22-honest-limitations)  
23. [Quick lookup index](#23-quick-lookup-index)  

---

## 1. Base paper (PhishLLM)

### 1.1 Full reference

**Title:** *Less Defined Knowledge and More True Alarms: Reference-based Phishing Detection without a Pre-defined Reference List*

**Authors:** Ruofan Liu, Yun Lin, Xianglin Teoh, Gongshen Liu, Zhiyong Huang, Jin Song Dong

**Venue:** 33rd USENIX Security Symposium (USENIX Security 2024)

**Official PDF:** https://www.usenix.org/conference/usenixsecurity24/presentation/liu-yupei  

**Public codebase (upstream):** https://github.com/Duanexiao/PhishLLM  

### 1.2 Problem the paper addresses

Traditional reference-based phishing detectors rely on a **fixed brand list** and heavy **visual logo matching**. That limits recall for:

- Lesser-known or regional brands  
- Pages where phishing intent is clearer in **text and interaction** than in logos  
- Attackers using **hosting domains**, **typosquatting**, and **prompt-injection-style** page text  

### 1.3 PhishLLM pipeline (four stages — conceptual)

The paper describes a pipeline that, for each webpage, roughly does:

| Stage | Role |
|------|------|
| **1. Brand recognition** | Infer which legitimate brand (if any) the page impersonates, using **logo OCR**, **logo captioning** (vision-language), and page context — without needing a pre-defined brand inventory as the only source of truth. |
| **2. CRP detection** | Decide if the page is a **credential-requiring page (CRP)** — i.e. asks for passwords, 2FA, wallet seed phrases, etc. |
| **3. CRP transition** | If the current view is not obviously CRP, optionally **interact** (e.g. click “Continue”) to reach a login surface (bounded hops). |
| **4. Validation + decision** | Apply rules such as **brand vs. registered domain mismatch**, **hosting-domain heuristics**, and **popularity / search-index validation**; fuse signals into a phishing verdict. |

### 1.4 Threat model (paper, summarised)

- Attacker controls page content and can try to **mislead** automated checks (e.g. text that looks benign).  
- Defender does **not** assume a static list of brands covers all targets.  
- Practical deployments care about **precision** (analyst trust) and **cost/latency** (API + compute).

### 1.5 Why this paper fits CS7602 “AI-driven search”

The paper’s design naturally exposes a **configuration space**: prompts, modality toggles, validation modes, fusion policies, interaction depth, thresholds. Your coursework asks for a **fixed evaluator** + **many candidates** + **search/analysis** — that maps directly to **searching over PhishLLM-style configs** rather than replicating the entire 12K-page benchmark or field study.

---

## 2. Course context (CS7602 / CS8602 case study)

**Theme:** Use AI as part of a **search process** over a security problem — not a one-off chat.

**Hard requirements (from the case study brief):**

- Candidate representation (e.g. JSON configs)  
- Fixed `evaluate(candidate) → metrics`  
- AI-driven loop that proposes **many** candidates  
- Selection / analysis (precision floors, Pareto points, failure modes)  
- README: install, small demo, reproduce findings at reduced scale  
- One-page case study (problem, solution generator, evaluator/metrics, results, search behaviour, lessons)  

This repository is structured to match those deliverables explicitly.

---

## 3. What this repository is — and what it is not

### 3.1 What it *is*

- A **self-contained Python package** (`phishllm_search`) that implements:  
  - JSON-schema **candidates**  
  - A **deterministic mock backend** that emulates PhishLLM-style trade-offs (for reproducible coursework)  
  - Optional **official-repo** and **replay** backends  
  - A full **evaluator** (metrics, confusion matrix, bootstrap recall CI, failure buckets)  
  - A **search loop** with heuristic and optional **LLM (Anthropic)** proposers  
  - **Reporting** (plots + tables + auto case-study draft)  
  - **Synthetic dataset generator** compatible with the upstream **per-site folder** layout  
  - **48 unit tests**  

### 3.2 What it is *not*

- It is **not** a full reimplementation of the USENIX paper’s exact models (CLIP transition model, real OCR/caption APIs, full Google Programmable Search integration).  
- It is **not** the official PhishLLM repository — but it provides a **documented adapter** to shell out to it.  
- The default **mock** backend is a **transparent rule-based emulator** so search behaviour and failure buckets are interpretable without API keys.

---

## 4. What is different or “your contribution” in this project

| Aspect | Typical “run the paper code once” | This project |
|--------|-----------------------------------|--------------|
| **Candidate space** | Fixed config in a script | Explicit **JSON Schema** + 8 seeds + mutations / LLM proposals |
| **Evaluation** | Ad-hoc runs | Fixed **`evaluate(candidate, dataset)`** with logged per-sample rows |
| **Metrics** | Accuracy only | Precision, recall, F1, FPR, FNR, runtime, cost, **bootstrap recall CI**, confusion matrix |
| **Diagnostics** | None | **8 failure buckets** aligned to paper-style error modes |
| **Search** | Manual trial | **Multi-round loop**: propose → evaluate → rank under precision floor → Pareto carry → stop rules |
| **Reproducibility** | Informal | Seeded dataset, seeded bootstrap, seeded heuristic proposer; **tests** lock behaviour |
| **Reporting** | None | Search trace, Pareto, failure bars, top-K CI plot, leaderboard CSV/MD |
| **HPC** | None | **Slurm** scripts for eval, array eval, full search |

**Intellectual focus:** *How do inference-time knobs interact?* For example: recall-oriented brand prompts can rescue “lesser-known brand” misses but may hallucinate brands on benign indie sites unless **robust** gating and **popularity validation** are set correctly — the mock backend and failure buckets make that visible **quantitatively**.

---

## 5. High-level architecture

```
configs/candidates/*.json ──┐
configs/schema/*.json      ├──► schema.validate ──► evaluate_candidate(dataset)
data/labels.csv + site_*/  ──┘                              │
                                                             ▼
                                                    backends.mock | official | replay
                                                             │
                                                             ▼
metrics.json + predictions.csv + failure_buckets ────────────┤
                                                             │
search_loop ◄── proposer (heuristic | LLM+fallback) ◄────────┘
     │
     ├──► runs/search/round_*/...  (per-candidate artifacts)
     ├──► search_summary.csv, top5.json, events.jsonl
     │
report ◄── reads runs/ + baseline/
     │
     └──► artifacts/plots, artifacts/tables, artifacts/case_study.md
```

---

## 6. Complete folder structure

Legend: paths below are relative to **`phishllm_final/`** (the repository root for code submission).

```
phishllm_final/
├── PROJECT_REFERENCE.md          ← This file (complete manual)
├── README.md                     ← Short user-facing quick start
├── LICENSE                       ← MIT
├── Makefile                      ← install, dataset, eval, search, report, demo, test, clean
├── pyproject.toml                ← package metadata, entry points, pytest config
├── requirements.txt              ← runtime deps
├── requirements-dev.txt          ← + pytest
│
├── case_study.md                 ← One-page case study (Markdown, submission-ready)
├── case_study.tex                ← Same content (LaTeX single-column)
│
├── configs/
│   ├── schema/
│   │   └── candidate.schema.json ← JSON Schema for every candidate
│   └── candidates/
│       ├── seed_baseline.json
│       ├── seed_recall_first.json
│       ├── seed_precision_first.json
│       ├── seed_low_cost.json
│       ├── seed_robust.json
│       ├── seed_balanced.json
│       ├── seed_visual_only.json
│       └── seed_no_validation.json
│
├── prompts/                      ← Human-readable prompt *specs* (used by meta-prompt + docs)
├── docs/                         ← Deeper design notes
├── slurm/                        ← Batch scripts
├── data/                         ← Generated dataset (see §12); may be empty except README after clean checkout
├── src/phishllm_search/          ← Python package
├── tests/                        ← pytest suite
├── runs/                         ← Evaluation/search outputs (often gitignored)
└── artifacts/                    ← Plots/tables from `report` (often gitignored)
```

---

## 7. Every tracked file — purpose

### 7.1 Root

| File | Purpose |
|------|---------|
| `PROJECT_REFERENCE.md` | **This document** — exhaustive reference for you and graders. |
| `README.md` | Install, demo, reproduction, CLI, limitations — kept practical and shorter. |
| `LICENSE` | MIT license text. |
| `Makefile` | `make install`, `dataset`, `eval-baseline`, `search`, `report`, `demo`, `test`, `clean`. |
| `pyproject.toml` | Package name `phishllm-search`, Python ≥3.9, dependencies, console scripts, pytest path. |
| `requirements.txt` | Pinned-style ranges for `jsonschema`, `numpy`, `pandas`, `matplotlib`, `PyYAML`; optional `anthropic` comment. |
| `requirements-dev.txt` | Includes `requirements.txt` + `pytest`, `pytest-cov`. |
| `case_study.md` | Final **one-page** write-up for the coursework (practitioner style). |
| `case_study.tex` | LaTeX version for PDF compilation. |

### 7.2 `configs/schema/candidate.schema.json`

Machine-readable **contract** for candidates: allowed enums, numeric ranges, required keys. Validated on load, after LLM proposals, and in tests.

### 7.3 `configs/candidates/*.json`

Eight **seed** configurations spanning baseline, recall-first, precision-first, low-cost, robust, balanced, visual-only ablation, and no-validation stress test. See §10.

### 7.4 `prompts/*.txt`

Text templates describing **brand**, **CRP**, and **meta-search** instructions. The mock backend encodes *behaviour* in code keyed by `brand_prompt` / `crp_prompt` string enums; these files document the *intent* and feed the **LLM meta-prompt** (`meta_search_prompt.txt`).

### 7.5 `docs/`

| File | Purpose |
|------|---------|
| `architecture.md` | ASCII architecture diagram + data flow. |
| `failure_catalog.md` | Failure bucket definitions and mapping to remedies. |
| `connecting_to_official_repo.md` | How to plug in real PhishLLM via `OfficialRepoBackend`. |
| `final_implementation_appendix.tex` | LaTeX appendix: midterm → final deltas. |

### 7.6 `slurm/`

| File | Purpose |
|------|---------|
| `run_eval.sbatch` | Single-candidate evaluation job. |
| `run_eval_array.sbatch` | Array job: one JSON per task index. |
| `run_search.sbatch` | Full search + report on cluster. |

### 7.7 `data/`

| Path | Purpose |
|------|---------|
| `README.txt` | Reminder to run `make dataset` if `labels.csv` missing. |
| `labels.csv` | Ground truth (generated): `site_id,label,target_brand,is_crp,notes`. |
| `site_XXX/` | Per-site folder: `info.txt` (URL), `html.txt` (HTML/text), optional `shot.png`. |

### 7.8 `tests/`

| File | What it tests |
|------|----------------|
| `conftest.py` | `PYTHONPATH`, tiny dataset fixture, sample candidate fixture. |
| `test_schema.py` | Valid/invalid candidates vs schema. |
| `test_metrics.py` | Classification metrics, bootstrap CI, median/percentile. |
| `test_failures.py` | Failure bucket classification edge cases. |
| `test_mock_backend.py` | Mock predictions for typosquat, injection, hosting, etc. |
| `test_evaluator.py` | End-to-end evaluator on tiny set, determinism, confusion sum. |
| `test_proposer.py` | Heuristic proposer validity and de-duplication. |
| `test_search_loop.py` | Selector, stopping, mini end-to-end search in `tmp_path`. |

### 7.9 `src/phishllm_search/` — see §8 for detail

Package entry: `__init__.py` (version), `__main__.py` (delegates to `cli`), `cli.py` (subcommands).

---

## 8. Source code — module by module

### 8.1 `cli.py`

Defines argparse subcommands:

| Subcommand | Role |
|------------|------|
| `genset` | Call `generate_dataset()` into `--out_dir`. |
| `eval` | Load one candidate JSON, run `evaluate_candidate`, write `metrics.json`, `predictions.csv`, `candidate.json`. |
| `search` | Run `run_search(SearchConfig)`; write rounds under `runs/search/`, summary CSV, `top5.json`, `events.jsonl`. **Logs → stderr**, final JSON summary → **stdout**. |
| `report` | Load search + optional baseline → plots, tables, optional `artifacts/case_study.md` from template. |

Entry points registered in `pyproject.toml`: `phishllm-eval`, `phishllm-search`, `phishllm-report`, `phishllm-genset`.

### 8.2 `schema.py`

Loads `candidate.schema.json` (path resolved relative to package layout), exposes `validate()`, `validate_many()`, `schema_summary()` (string for LLM prompts).

### 8.3 `dataset.py`

`Sample` dataclass; `load_samples(dataset_dir)` reads `labels.csv` and each `site_id/info.txt` + `html.txt`. `stratified_split()` optional helper.

### 8.4 `genset.py`

Deterministic generator: **6 phishing templates × 12** + **7 benign templates × 10** = **142** samples default (`seed=7`). Implements brand mismatch, typosquat, hidden login, prompt injection, crypto, lesser-known enterprise, plus benign logins, dashboards, aliases, blogs, status pages, **indie lookalike URLs**, **hosted dev sites**.

### 8.5 `backends/`

| Module | Role |
|--------|------|
| `base.py` | `Prediction` dataclass + `Backend` protocol. |
| `mock.py` | **Main coursework backend:** rules for brand, CRP, transition, popularity, hosting, fusion; exposes trade-offs. |
| `official.py` | Runs user shell command with env vars; parses last line of stdout as JSON prediction. |
| `replay.py` | Reads cached `<site_id>.json` per sample. |
| `__init__.py` | `make_backend(candidate)` factory. |

### 8.6 `evaluator/`

| Module | Role |
|--------|------|
| `runner.py` | **`evaluate_candidate()`** — loop samples, call backend, aggregate metrics, write-style rows. |
| `metrics.py` | `ClassificationMetrics`, `bootstrap_recall_ci`, `median`, `percentile`. |
| `failures.py` | `classify_failure()`, `FAILURE_BUCKET_KEYS`, `empty_buckets()`. |
| `confusion.py` | 2×2 confusion dict + pretty lines. |

### 8.7 `search/`

| Module | Role |
|--------|------|
| `loop.py` | **`run_search()`** — rounds, evaluate pool, rank, build `ProposerContext`, propose, stopping, append `events.jsonl`. |
| `selector.py` | Precision-floor ordering, `pareto_frontier()`, `diverse_candidate()`. |
| `stopping.py` | `StopReason`, `StoppingState`, `evaluate_stopping()`. |
| `proposers/base.py` | `ProposerContext` dataclass. |
| `proposers/heuristic.py` | Bias from failure buckets → mutations. |
| `proposers/llm.py` | Anthropic Messages API + parse JSON array + validate + dedupe; fallback to heuristic. |

### 8.8 `reporting/`

| Module | Role |
|--------|------|
| `plots.py` | Matplotlib: search trace, Pareto, failures per round, confusion heatmap, top-K recall CI. |
| `tables.py` | Leaderboard, failures per round, baseline vs best, seeds round 0. |
| `case_study.py` | Fills template paragraph from `search_summary`, `top5`, `events`, dataset counts → `artifacts/case_study.md`. |

### 8.9 `utils/`

| Module | Role |
|--------|------|
| `hashing.py` | `candidate_hash()` for de-duplication (ignores `name`, `hypothesis`). |
| `logging.py` | `get_logger()`, `JsonlWriter` for structured events. |

---

## 9. Candidate JSON schema

**Location:** `configs/schema/candidate.schema.json`

**Required fields (conceptual):**

| Field | Meaning |
|-------|---------|
| `name` | Unique run label. |
| `backend` | `mock` \| `official_repo` \| `replay`. |
| `brand_prompt` | `brand_default_v1` \| `brand_recall_v1` \| `brand_precision_v1` \| `brand_robust_v1`. |
| `crp_prompt` | `crp_default_v1` \| `crp_recall_v1` \| `crp_precision_v1` \| `crp_robust_v1`. |
| `use_logo_ocr`, `use_logo_caption` | Modality cost/latency toggles (mock uses them in timing/cost rules). |
| `prompt_defense` | If false + non-robust CRP → injection can force `crp=false` in mock. |
| `popularity_validation` | `google-indexed` \| `cached` \| `disabled`. |
| `hosting_rule` | `strict` \| `relaxed`. |
| `max_interactions` | 0–2 (CRP transition hops in mock). |
| `brand_confidence_min` | 0.5–0.95 threshold for “strong enough” brand signal in fusion. |
| `report_policy` | `mismatch_and_crp` \| `mismatch_or_crp` \| `score_only`. |
| `temperature` | Recorded for reproducibility (mock does not call an LLM). |
| `runtime_budget_sec` | Recorded; evaluator sets `respects_runtime_budget` vs median runtime. |

**Optional / backend-specific:** `official_repo_root`, `official_repo_command`, `replay_dir`, `hypothesis` (for search logging).

---

## 10. Seed candidates (configs)

| File | Intent |
|------|--------|
| `seed_baseline.json` | Paper-style default: both modalities, Google validation, strict hosting, 1 interaction, AND fusion, threshold 0.8. |
| `seed_recall_first.json` | Lower threshold, OR fusion, recall prompts — stresses FP vs FN trade-off. |
| `seed_precision_first.json` | Higher threshold, precision prompts, no extra interaction. |
| `seed_low_cost.json` | No caption, cached validation, relaxed hosting, 0 interactions. |
| `seed_robust.json` | Robust brand + CRP prompts; URL-stem fallback gated on suspicious signals in mock. |
| `seed_balanced.json` | Robust brand + default CRP + cached validation + 1 interaction. |
| `seed_visual_only.json` | **Ablation:** `prompt_defense=false` to show injection sensitivity. |
| `seed_no_validation.json` | **Stress:** `popularity_validation=disabled` — demonstrates alias FP storm in metrics. |

---

## 11. Prompt templates

| File | Role |
|------|------|
| `brand_default_v1.txt` | Balanced brand instructions. |
| `brand_recall_v1.txt` | Biased toward recalling a brand from weak cues. |
| `brand_precision_v1.txt` | Requires corroboration before brand call. |
| `brand_robust_v1.txt` | Ignores injection-like claims; typo-squat awareness. |
| `crp_default_v1.txt` | Standard CRP + transition hint. |
| `crp_recall_v1.txt` | Broader CRP cues. |
| `crp_precision_v1.txt` | Stricter credential field requirement. |
| `crp_robust_v1.txt` | Injection-resistant CRP semantics. |
| `meta_search_prompt.txt` | Instructions for the **LLM proposer** (schema summary, constraints, JSON array output). |

---

## 12. Synthetic dataset (`genset`)

**Generator:** `src/phishllm_search/genset.py`  
**CLI:** `python -m phishllm_search.cli genset --out_dir data [--seed 7]`  
**Default size:** **142** sites = 6×12 phishing + 7×10 benign.

**Phishing templates (6):**

1. Brand mismatch on suspicious TLD  
2. Typosquat domain  
3. Hidden login behind “Continue” on hosting domain  
4. Prompt-injection disclaimers in HTML  
5. Crypto / wallet wording without classic “password”  
6. Lesser-known enterprise brand portal  

**Benign templates (7):**

1. Legitimate brand login on real domain  
2. Account dashboard (no credential form)  
3. Legitimate alias domain (e.g. `fb.com` → facebook)  
4. Blog mentioning passwords (informational only)  
5. Status page  
6. Indie business with **brand-like URL stem** (adversarial for recall prompts)  
7. Legitimate project page on `vercel.app` / `github.io` / etc.  

**Per-site files:** `info.txt` (single-line URL), `html.txt` (raw HTML snippet). Screenshots optional for official backend.

---

## 13. Evaluator contract

**Function:** `evaluate_candidate(candidate, dataset_dir, bootstrap_iters=1000, seed=0)` → `EvalResult`

**Outputs:**

- `metrics` dict: precision, recall, F1, FPR, FNR, accuracy, tp/fp/tn/fn, `recall_ci_lo/hi`, median and p95 runtime, estimated cost per 1K pages, failure bucket counts, confusion matrix, flags for precision floor and runtime budget vs candidate.  
- `rows`: list of per-sample dicts (for `predictions.csv`).  

**Invariant:** Confusion matrix cells sum to `num_samples`.

---

## 14. Failure buckets

Defined in `evaluator/failures.py`:

| Bucket | Typical meaning |
|--------|------------------|
| `brand_hallucination` | Benign classified as phish; predicted brand ≠ ground-truth brand (or empty target). |
| `alias_false_positive` | Legitimate alias flagged when validation off (also surfaced in mock reasons). |
| `brand_miss` | Phish classified as benign; no brand inferred. |
| `crp_miss` | Phish as benign; CRP false. |
| `hidden_login_miss` | Notes indicate hidden login; FN. |
| `fusion_miss` | Brand and CRP true but decision still benign (score/policy). |
| `prompt_injection_failure` | CRP stage returns injection failure reason. |
| `api_or_parser_failure` | Backend exception or parse error. |

---

## 15. Search loop

1. Load seeds; hash seen configs.  
2. For each round: evaluate pool; write `round_N/<name>/metrics.json`, `candidate.json`, `predictions.csv`.  
3. Rank by precision floor lexicographic key: `(floor_ok, recall, F1, -runtime, -cost)`.  
4. Summarise round to `round_N_summary.json`.  
5. Build `ProposerContext` (top-K metrics, diverse low scorer, aggregated failure buckets).  
6. Proposer returns new candidates; de-dup by `candidate_hash`.  
7. Stopping: empty pool, max rounds, or no recall gain under floor for patience rounds.  
8. Write `search_summary.csv`, `top5.json`, `events.jsonl`.

---

## 16. Backends

| `backend` value | When to use |
|-------------------|------------|
| `mock` | Default; no API keys; deterministic; for coursework demos and CI. |
| `official_repo` | You have PhishLLM cloned and a wrapper command that prints one JSON line per sample. |
| `replay` | You cached predictions and want fast repeated search iterations. |

---

## 17. Reporting

**CLI:** `report --search_dir --baseline_dir --dataset --out_dir`

**Plots (PNG + PDF):** search trace, Pareto recall vs runtime, failure buckets stacked by round, top candidate confusion matrix, top-K recall with bootstrap error bars.

**Tables:** leaderboard top 10, failures per round, seeds round 0, baseline vs best.

**Note:** Hand-curated **`case_study.md`** at repo root is the submission-grade narrative; **`artifacts/case_study.md`** is auto-generated from metrics and may differ in wording.

---

## 18. Commands, Makefile, reproducibility

| Command | Effect |
|---------|--------|
| `make install` | `pip install -r requirements.txt` |
| `make dev-install` | Includes pytest |
| `make dataset` | Generate `data/` |
| `make eval-baseline` | Evaluates `seed_baseline.json` |
| `make search ROUNDS=4 PROPOSER=heuristic` | Full search |
| `make report` | Needs `runs/search` + `runs/baseline` |
| `make demo` | dataset + baseline + 1 search round + report |
| `make test` | pytest |

**Reproducibility:** dataset seed, bootstrap seed, heuristic proposer seed, and per-round evaluation seed offset are wired in config/CLI. LLM proposer is non-deterministic unless temperature 0 and API stable; **fallback heuristic** is always deterministic.

**Important:** `search` prints progress to **stderr**; final JSON to **stdout** — do not merge streams if parsing JSON programmatically.

---

## 19. Tests

Run: `PYTHONPATH=src python3 -m pytest tests/ -v`

**Count:** 48 tests (as of last run). They guard schema, maths, mock behaviour, evaluator invariants, proposer, and a miniature full search.

---

## 20. Slurm / HPC

Scripts assume `conda activate phishllm-search` (or override `CONDA_ENV`). Submit with `sbatch`; export `CANDIDATE`, `DATASET`, `OUT_DIR`, or array indices as documented in headers.

---

## 21. Generated outputs (not always in git)

`.gitignore` typically excludes:

- `runs/` contents (keeps `.gitkeep`)  
- `artifacts/plots/*.{png,pdf}`, `artifacts/tables/*.{csv,md}`, `artifacts/logs/*.jsonl`  
- `data/labels.csv`, `data/site_*` (optional; `data/README.txt` kept)  
- `.pytest_cache`, `__pycache__`

**Regenerate:** `make dataset && make demo` or full `make search && make report`.

---

## 22. Honest limitations

1. **Mock ≠ paper numbers:** The mock encodes *qualitative* trade-offs, not PhishLLM’s published precision/recall on 12K pages.  
2. **Synthetic data:** 142 sites are *templates*; they are stratified for teaching/search, not a real crawl.  
3. **LLM proposer:** Optional; coursework headline runs use **heuristic** proposer for marker-verifiable reproducibility.  
4. **Real deployment:** Would require `official_repo` or `replay` from real inference + real labels.

---

## 23. Quick lookup index

| I need to… | Open |
|------------|------|
| Run the project fast | `README.md` → `make demo` |
| Understand one file | §7 + §8 in **this** doc |
| Paper citation & problem | §1 |
| Why this is “AI search” coursework | §2, §4 |
| Candidate field meanings | §9 |
| What each seed does | §10 |
| Failure bucket definitions | §14 |
| Plug in real PhishLLM | `docs/connecting_to_official_repo.md` |
| Diagram | `docs/architecture.md` |
| Midterm → final narrative | `docs/final_implementation_appendix.tex` |
| One-page write-up | `case_study.md` or `case_study.tex` |

---

**End of PROJECT_REFERENCE.md** — maintain this file when you add modules, seeds, or buckets so the repository stays self-explanatory for you, your supervisor, and coursework markers.
