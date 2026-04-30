# Connecting to the Official PhishLLM Repository

Our `OfficialRepoBackend` is a thin shell-out wrapper. It does not parse the
upstream repository's internal logs — it expects a single user-supplied
shell command that runs the official inference for one site and prints a
**single-line JSON object** on the last line of stdout.

## The contract

The wrapper passes the following environment variables to your shell command:

| Variable                     | Description |
|------------------------------|-------------|
| `PHISHLLM_CANDIDATE_JSON`    | The full candidate JSON, encoded as a string. |
| `PHISHLLM_URL`               | The site URL (`info.txt` content). |
| `PHISHLLM_SITE_ID`           | The site id (e.g. `site_007`). |
| `PHISHLLM_SHOT`              | (optional) absolute path to `shot.png` if it exists. |

The command must print, on its **last stdout line**, a JSON object with
the same fields as `phishllm_search.backends.base.Prediction`:

```json
{
  "pred_label": "phish",
  "pred_brand": "paypal.com",
  "brand_confidence": 0.93,
  "brand_source": "ocr+caption",
  "crp": true,
  "crp_reason": "explicit_credential_field",
  "reasons": ["brand=paypal.com", "credential_taking", "suspicious_domain"],
  "runtime_sec": 3.41,
  "estimated_cost": 0.0023
}
```

## Worked example

Assume the upstream repo is checked out at `$HOME/PhishLLM` and its
inference script is `scripts/infer/test.py`. Create a thin adapter
`scripts/infer_one.py`:

```python
import json, os, sys, time
candidate = json.loads(os.environ["PHISHLLM_CANDIDATE_JSON"])
url       = os.environ["PHISHLLM_URL"]
site_id   = os.environ["PHISHLLM_SITE_ID"]
# ... run the upstream pipeline using `candidate` to switch prompts ...
result = {
    "pred_label": predicted_label,
    "pred_brand": predicted_brand,
    "brand_confidence": float(brand_confidence),
    "brand_source": "ocr+caption",
    "crp": bool(crp),
    "crp_reason": crp_reason,
    "reasons": reasons,
    "runtime_sec": runtime,
    "estimated_cost": estimated_cost,
}
print(json.dumps(result))
```

Then point your candidate JSON at it:

```json
{
  "name": "official_baseline",
  "backend": "official_repo",
  "official_repo_root": "/home/user/PhishLLM",
  "official_repo_command": "python scripts/infer_one.py",
  "brand_prompt": "brand_default_v1",
  "crp_prompt": "crp_default_v1",
  ...
}
```

The rest of the search pipeline is unchanged — `evaluate(candidate, dataset)`
will simply shell out to your adapter for each sample. The reduced split's
folder layout (`data/<site_id>/{info.txt,html.txt,shot.png}`) is identical
to the upstream repo's expected layout, so no data conversion is required.

## Caching upstream calls

Real-world API calls are non-trivial; cache the upstream output once and
replay during the search. Run the official backend on each candidate once
and write `runs/cache/<candidate_hash>/<site_id>.json` with the same JSON
schema as above. Then switch the candidate to:

```json
{
  "backend": "replay",
  "replay_dir": "runs/cache/<candidate_hash>"
}
```

The `ReplayBackend` reads predictions from disk, so the search loop
iterates without re-incurring API cost.
