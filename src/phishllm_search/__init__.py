"""phishllm_search.

AI-driven configuration search over a PhishLLM-style reference-based phishing
detector. The package is structured around three contracts:

* ``Candidate``  - a JSON-validated configuration of the detector.
* ``Evaluator``  - a fixed deterministic ``evaluate(candidate, dataset)`` that
  returns a metrics dict and a per-sample log.
* ``Proposer``   - a stateless object that turns evaluation feedback into new
  candidates (heuristic mutation, LLM, or grid).

The search loop ties them together with a Pareto/precision-floor selector and
explicit stopping criteria.
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("phishllm-search")
except PackageNotFoundError:  # pragma: no cover - editable / source installs
    __version__ = "1.0.0"

__all__ = ["__version__"]
