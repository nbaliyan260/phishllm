# Failure-Mode Catalog

The evaluator classifies each error into exactly one bucket. The order of
the checks matters — earlier checks correspond to more specific (and more
actionable) failures. The full list lives in
`src/phishllm_search/evaluator/failures.py`.

| Bucket | When it fires | Typical fix |
|---|---|---|
| `brand_hallucination` | benign predicted as phishing AND a brand was attributed AND the attributed brand differs from the page's known brand (or the page has no associated brand). | Tighten brand keyword matching to word boundaries; require a corroborating signal (suspicious TLD / hosting domain) before URL-stem fallback fires. |
| `alias_false_positive` | benign predicted as phishing because a popular alias (e.g. `fb.com -> facebook.com`) was misread as a brand mismatch. | Re-enable `popularity_validation` (Google-indexed or cached); resolve aliases before computing `brand_mismatch`. |
| `brand_miss` | phishing predicted as benign AND the brand stage produced no candidate brand. | Switch to `brand_recall_v1` or `brand_robust_v1`, or lower `brand_confidence_min`. |
| `crp_miss` | phishing predicted as benign AND no CRP signal was detected. | Switch to `crp_recall_v1`, or relax the CRP prompt; consider raising `max_interactions`. |
| `hidden_login_miss` | phishing predicted as benign AND the sample is annotated as a hidden-login case AND the CRP detector did not fire. | Set `max_interactions >= 1` so the CRP transition stage can hop to the login UI. |
| `fusion_miss` | phishing predicted as benign even though both the brand and the CRP signals fired (i.e. the score sum was below the report threshold). | Switch from `mismatch_and_crp` to `mismatch_or_crp`, or lower `brand_confidence_min`. |
| `prompt_injection_failure` | a CRP-stage decision was overturned by adversarial markers in the page (`ignore previous instructions`, `not a credential page`, ...). | Keep `prompt_defense=true` and use `crp_robust_v1`. |
| `api_or_parser_failure` | the backend raised an exception (e.g. official-repo adapter broke) or returned malformed JSON. | Inspect `runs/<round>/<name>/predictions.csv` for the offending row and the upstream repo's stderr. |

## Mapping to the paper

The first six buckets directly map to the failure categories listed in
Section 7 of Liu et al. (2024). `prompt_injection_failure` is our
explicit operationalisation of the adversarial-prompt resilience the
paper discusses qualitatively. `api_or_parser_failure` is an operational
bucket (not in the paper) that prevents one broken backend call from
silently inflating other buckets.

## Cross-reference: bucket -> dominant remedy in the search

The heuristic proposer's bias function (`HeuristicProposer._failure_bias`)
maps the dominant failure bucket to one of five mutation classes:

| Dominant bucket(s) | Mutation class chosen first |
|---|---|
| precision floor breach (any) | `precision`: high threshold, AND-fusion, precision prompts |
| `prompt_injection_failure` | `robustness`: robust prompts + `prompt_defense=true` |
| `alias_false_positive` | `validation`: enable popularity validation, strict hosting |
| `crp_miss` or `hidden_login_miss` | `recall`: lower threshold, recall prompts, OR-fusion |
| cost > budget | `cost`: cached validation, drop caption modality |

This is exactly the failure-feedback structure the LLM proposer is also
asked to reason over in its structured JSON meta-prompt (built in
`src/phishllm_search/search/proposers/llm_proposer.py::_build_meta_prompt`).
