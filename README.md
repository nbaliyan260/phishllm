# PhishLLM-Search

AI-driven configuration search for a PhishLLM-style reference-based phishing
detector — the final coursework project for **CS7602: Using AI to Explore a
Security Research Problem**, by **Nazish Baliyan**.

**Full manual (paper, every file, architecture, metrics):** see [`PROJECT_REFERENCE.md`](PROJECT_REFERENCE.md).

> Selected paper: Liu et al., *Less Defined Knowledge and More True Alarms:
> Reference-based Phishing Detection without a Pre-defined Reference List*,
> USENIX Security 2024
> [\[paper\]](https://www.usenix.org/conference/usenixsecurity24/presentation/liu-yupei)
> [\[code\]](https://github.com/Duanexiao/PhishLLM)

This repository implements the **midterm contract** end-to-end:

| | |
|---|---|
| **Candidate** | a JSON object validated against `configs/schema/candidate.schema.json` |
| **Evaluator** | a fixed `evaluate(candidate, dataset) -> metrics_dict` (`src/phishllm_search/evaluator/`) |
| **Search loop** | propose → evaluate → select → stop, with two interchangeable proposers (heuristic / LLM) |

The pipeline runs end-to-end on a synthetic 142-site dataset that covers the six
failure modes the paper catalogues (brand mismatch, typo-squat, hidden login,
prompt injection, crypto phishing, lesser-known brands), plus two adversarial
benign categories (indie sites with brand-like URL stems, dev projects on
hosting platforms). The search loop produces tens of evaluated candidates,
structured logs, plots, ranked tables, and a one-page practitioner case study.

---

## Repository layout

```
phishllm_final/
├── README.md                       <- you are here
├── case_study.md                   <- one-page practitioner case study
├── case_study.tex                  <- single-column LaTeX version of the same
├── pyproject.toml                  <- modern Python project metadata
├── requirements.txt
├── requirements-dev.txt
├── Makefile                        <- common workflows
├── configs/
│   ├── candidates/                 <- 8 seed candidate JSONs
│   └── schema/
│       └── candidate.schema.json   <- the JSON Schema the evaluator validates against
├── prompts/                        <- brand / CRP prompt variants + meta-search prompt
├── data/                           <- empty until `make dataset` (142 per-site folders + labels.csv)
├── src/
│   └── phishllm_search/
│       ├── backends/               <- mock / official / replay
│       ├── evaluator/              <- metrics, failure buckets, confusion matrix, runner
│       ├── search/                 <- proposers, selector, stopping, loop
│       ├── reporting/              <- plots, tables, case-study generator
│       ├── utils/
│       ├── cli.py
│       ├── dataset.py
│       ├── genset.py
│       └── schema.py
├── tests/                          <- 48 unit tests
├── slurm/                          <- ready-to-submit HPC scripts
├── runs/                           <- search outputs (gitignored)
└── artifacts/                      <- plots, tables, case study (gitignored)
```

---

## 1. Install

Tested on Python 3.9 – 3.12. Only standard scientific dependencies are needed
to run the deterministic pipeline:

```bash
python3 -m pip install -r requirements.txt
# or, with dev tooling:
python3 -m pip install -r requirements-dev.txt
```

### Optional LLM Proposer Support

The pipeline ships with a **deterministic heuristic proposer** that requires
no API keys and runs fully offline — this is the configuration used by
`make demo`, all unit tests, and the headline results in this README. You
do not need to enable any LLM provider to reproduce the reported numbers.

On top of that, two optional LLM providers can be plugged in through a
single unified proposer (`LLMProposer`). The proposer auto-detects which
one to use from the environment; if neither is available it transparently
falls back to the heuristic proposer so the pipeline **never crashes when
run offline**.

| Provider | Model | Env var | Install |
|----------|-------|---------|---------|
| Anthropic Claude | `claude-3-haiku-20240307` | `ANTHROPIC_API_KEY` | `pip install "anthropic>=0.34"` |
| Google Gemini    | `gemini-1.5-flash`        | `GEMINI_API_KEY`    | `pip install "google-generativeai>=0.5,<1.0"` |

Enable whichever you prefer:

```bash
# Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
make search PROPOSER=anthropic

# Google Gemini
export GEMINI_API_KEY="..."
make search PROPOSER=gemini

# Let the pipeline pick automatically (Anthropic > Gemini > heuristic)
make search PROPOSER=auto
```

Determinism is preserved: evaluation is always seeded, schema-validated,
and identical to the heuristic run for any candidate the LLM actually
produces. Any LLM failure (missing SDK, network error, malformed JSON,
schema-invalid proposal, duplicate candidate, etc.) automatically falls
back to the heuristic mutator.

When an LLM call does run, cumulative token usage and an **estimated
USD cost** are written to `runs/search/llm_cost_summary.json` at the end
of the search. No cost file is written for pure-heuristic runs.

> **Security note.** Do not paste API keys into prompts, READMEs, chat
> windows, or commits. If you have already done so, revoke the key in
> the provider console and generate a fresh one. The code reads keys
> only from the environment variables above; keys are never persisted
> by this repository.

---

## 2. Quick demo (≈10 seconds)

```bash
make demo
```

This runs:

1. `phishllm-search genset` — synthesise a 142-site evaluation dataset.
2. `phishllm-search eval` — evaluate the baseline candidate.
3. `phishllm-search search` — one heuristic search round.
4. `phishllm-search report` — render plots, leaderboards, and the case study.

Outputs land in `runs/` (per-candidate metrics, predictions, structured event
logs) and `artifacts/` (plots in PNG+PDF, Markdown+CSV tables, and the
case study).

---

## 3. Full reproduction (key findings)

```bash
make dataset                    # data/labels.csv + 142 per-site folders
make eval-baseline              # runs/baseline/{metrics.json, predictions.csv, candidate.json}
make search ROUNDS=4 SEED=7     # 4 search rounds, deterministic
make report                     # artifacts/plots, artifacts/tables, case_study.md
```

To switch from the deterministic heuristic proposer to Claude:

```bash
export ANTHROPIC_API_KEY="..."
make search PROPOSER=llm
```

Reproducibility is enforced at every step: the dataset is seeded from
`SEED`, the evaluator is deterministic for the mock backend, the bootstrap
recall CI uses a seeded `random.Random`, the heuristic proposer is seeded,
and the LLM proposer falls back deterministically on any error.

---

## 4. Headline finding

Running the full search on the bundled dataset:

| Metric                  | Baseline (`seed_baseline`) | Best (`round2_thr90`) |
|-------------------------|---------------------------:|----------------------:|
| Precision               | 1.000                      | 1.000                 |
| Recall                  | 0.736                      | **1.000**             |
| F1                      | 0.848                      | **1.000**             |
| FPR                     | 0.000                      | 0.000                 |
| FNR                     | 0.264                      | **0.000**             |
| Median runtime / page   | 1.70 s                     | **0.55 s**            |
| Estimated cost / 1K     | \$2.30                     | **\$0.50**            |

The search reaches a candidate that **dominates the baseline on every axis**.
The full leaderboard, search trace, and Pareto frontier are in
`artifacts/`. The most informative failure-bucket finding is that
disabling `popularity_validation` produces 50 alias false-positives on this
dataset (`seed_no_validation`) — a quantitative confirmation that the paper's
validation stage is load-bearing rather than ornamental.

Two of the eight seeds (`seed_recall_first`, `seed_no_validation`) are
deliberately designed to **violate** the 0.95 precision floor. They are
included so the search loop has something visible to fix; without them the
baseline already meets the floor and the search has nothing to learn.

---

## 5. CLI reference

```bash
python3 -m phishllm_search.cli genset --out_dir DATA [--seed N]
python3 -m phishllm_search.cli eval   --candidate CFG.json --dataset DATA --out_dir DIR
python3 -m phishllm_search.cli search --dataset DATA --candidate_dir DIR \
                                      --out_dir DIR --rounds N \
                                      --proposer {heuristic,llm} --seed N
python3 -m phishllm_search.cli report --search_dir DIR --baseline_dir DIR \
                                      --dataset DATA --out_dir DIR
```

After `pip install -e .` the same commands are available as
`phishllm-eval`, `phishllm-search`, `phishllm-report`, `phishllm-genset`.

---

## 6. Tests

```bash
make test
# or
PYTHONPATH=src python3 -m pytest tests/ -q
```

48 tests cover:

- JSON schema validation & error reporting (`test_schema.py`)
- classification, bootstrap-CI, and percentile metrics (`test_metrics.py`)
- failure-bucket classification (`test_failures.py`)
- mock backend behaviour for every prompt / policy combination
  (`test_mock_backend.py`)
- end-to-end evaluator determinism + confusion-matrix invariants
  (`test_evaluator.py`)
- heuristic proposer mutation correctness (`test_proposer.py`)
- search loop end-to-end + selector + stopping rules (`test_search_loop.py`)

---

## 7. HPC / Slurm

`slurm/` contains three ready-to-submit scripts:

| Script              | Purpose |
|---------------------|---------|
| `run_eval.sbatch`   | evaluate one candidate on the full split |
| `run_eval_array.sbatch` | array job: one candidate per task |
| `run_search.sbatch` | run the AI-driven search loop |

All scripts assume a conda environment named `phishllm-search` with the
contents of `requirements.txt`.

---

## 8. Connecting to the official PhishLLM repo

Set `"backend": "official_repo"` in any candidate JSON and provide an
`official_repo_command` that runs the upstream inference and prints a
single-line JSON prediction on its last stdout line. The candidate JSON, the
URL, the site id and (optionally) the screenshot path are passed to the
command via the environment variables `PHISHLLM_CANDIDATE_JSON`,
`PHISHLLM_URL`, `PHISHLLM_SITE_ID`, and `PHISHLLM_SHOT`. See
`src/phishllm_search/backends/official.py` for the contract.

A typical setup:

```bash
git clone https://github.com/Duanexiao/PhishLLM.git $HOME/PhishLLM
cd $HOME/PhishLLM && ./setup.sh && conda activate phishllm
printf "%s\n" "$OPENAI_API_KEY" > ./datasets/openai_key.txt
printf "%s\n%s\n" "$GOOGLE_API_KEY" "$GOOGLE_SEARCH_ENGINE_ID" \
    > ./datasets/google_api_key.txt
```

After that, replace `"backend": "mock"` with `"backend": "official_repo"`
in your candidate and re-run `phishllm-search eval ...`.

---

## 9. Honest limitations

- The mock backend is a transparent rule emulator, not the real PhishLLM
  pipeline. It is intentionally simple so the search trade-offs are
  legible, but it does not reproduce every nuance of the paper's logo OCR
  / logo captioning / Google Programmable Search Engine integration. The
  `OfficialRepoBackend` is the path to a fully faithful evaluation.
- The dataset is synthetic (142 samples). The paper uses ~12K samples.
  A reduced split is permitted by the course brief and is the right scope
  for a 2-day midterm + 3-day final submission.
- The LLM proposer was implemented and tested, but the headline numbers in
  this README come from the deterministic heuristic proposer so that the
  results are reproducible without any API key. Switching to Claude is a
  one-line change.

---

## 10. Citation

If you use this code, please cite the original paper:

```
@inproceedings{liu2024phishllm,
  title={Less Defined Knowledge and More True Alarms: Reference-based
         Phishing Detection without a Pre-defined Reference List},
  author={Liu, Ruofan and Lin, Yun and Teoh, Xianglin and Liu, Gongshen
          and Huang, Zhiyong and Dong, Jin Song},
  booktitle={33rd USENIX Security Symposium (USENIX Security 24)},
  year={2024}
}
```
