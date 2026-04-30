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
                  |   heuristic | LLM       |
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
| LLM proposer (Claude) | `temperature=0.4` for diversity, but de-duplication on `candidate_hash` keeps the search non-degenerate; on any error the fallback heuristic proposer kicks in deterministically |

Reproducing the headline numbers therefore requires only `--seed 7`.
