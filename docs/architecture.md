# Architecture

```
                 +---------------------------+
                 |  configs/candidates/*.json|
                 |        seed candidates    |
                 +-------------+-------------+
                               |
                               v
+-----------------+   +--------+--------+   +-------------------------+
|   genset CLI    |   |  Schema validate|   |  prompts/*.txt          |
|  (data/*)       |-->|  (jsonschema)   |   |  brand/CRP/meta-search  |
+-----------------+   +--------+--------+   +-------------+-----------+
                               |                          |
                               v                          v
+--------+    +----------------+----------------+   +-----+-----+
| labels |--> |  evaluate(candidate, dataset)   |<--+  Backend   |
| .csv   |    |  - per-sample prediction        |   |  mock|repo |
+--------+    |  - precision/recall/F1/FPR/FNR  |   |  |replay   |
              |  - bootstrap recall CI          |   +------------+
              |  - failure-bucket histogram     |
              |  - confusion matrix             |
              +----------------+----------------+
                               |
                               v
                  +------------+------------+
                  |  precision_floor_selector
                  |  + pareto_frontier      |
                  |  + diverse_candidate    |
                  +------------+------------+
                               |
                               v
                  +------------+------------+
                  |     Proposer            |
                  |  heuristic | LLM unified |
                  |  (anthropic|gemini|auto) |
                  |  (uses ProposerContext) |
                  +------------+------------+
                               |
                               v
                       new candidates
                               |
                  +------------+------------+
                  |    Stopping rules       |
                  |  max_rounds | no_gain   |
                  |  | empty_round         |
                  +------------+------------+
                               |
                               v
                  +------------+------------+
                  |    Reporting            |
                  |  - 5 plots (PNG/PDF)    |
                  |  - 4 tables (MD/CSV)    |
                  |  - case_study.md        |
                  |  - events.jsonl         |
                  +-------------------------+
```

## Data flow

1. **`genset`** generates a 142-site dataset under `data/` using deterministic
   templates (six phishing failure modes + seven benign categories).
2. **`evaluate`** loads `data/labels.csv`, runs the chosen backend on each
   sample, and aggregates a metrics dict + a per-sample row dump.
3. **`search`** evaluates each seed in round 0; in subsequent rounds it
   builds a `ProposerContext` (top-K, diverse under-performer, failure
   summary, schema, budgets) and asks the proposer for new candidates.
4. **`report`** reads `runs/search/search_summary.csv`, `events.jsonl`,
   `top5.json`, and `runs/baseline/metrics.json` to render plots, tables,
   and the one-page case study.

## Determinism contract

| Component             | Determinism guarantee |
|-----------------------|------------------------|
| `genset`              | seeded `random.Random(seed)` |
| Mock backend          | pure functions of `(sample, candidate)` |
| Bootstrap recall CI   | seeded `random.Random(seed + round_idx)` |
| Heuristic proposer    | seeded `random.Random(seed)` |
| LLM proposer (unified) | Anthropic Claude (`claude-3-haiku-20240307`) or Google Gemini (`gemini-1.5-flash`) at `temperature=0`; schema validation + `candidate_hash` dedup keep the search non-degenerate. On missing SDK, missing API key, HTTP error, malformed JSON, schema-invalid candidate, or all-duplicates the deterministic heuristic fallback kicks in transparently, so the pipeline is always runnable offline. |

Reproducing the headline numbers therefore requires only `--seed 7`.
