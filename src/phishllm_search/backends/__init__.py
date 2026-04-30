"""Backend implementations for the PhishLLM evaluator.

A backend takes a ``Sample`` and a candidate config and returns a structured
prediction dictionary. Three implementations are provided:

* ``MockPhishLLMBackend`` - deterministic, dependency-free, used for the
  reproducible demo and unit tests.
* ``OfficialRepoBackend`` - thin shell-out wrapper around the upstream
  PhishLLM repository (https://github.com/Duanexiao/PhishLLM).
* ``ReplayBackend``       - replays previously cached predictions, used to
  iterate on the search loop without re-incurring API cost.
"""

from .base import Backend, Prediction
from .mock import MockPhishLLMBackend
from .official import OfficialRepoBackend
from .replay import ReplayBackend


def make_backend(candidate: dict) -> Backend:
    """Instantiate the backend selected by ``candidate['backend']``."""
    backend = candidate.get("backend", "mock")
    if backend == "mock":
        return MockPhishLLMBackend()
    if backend == "official_repo":
        repo_root = candidate.get("official_repo_root", ".")
        return OfficialRepoBackend(repo_root=repo_root)
    if backend == "replay":
        replay_dir = candidate.get("replay_dir")
        if not replay_dir:
            raise ValueError("backend=replay requires 'replay_dir' in the candidate")
        return ReplayBackend(replay_dir=replay_dir)
    raise ValueError(f"Unknown backend: {backend!r}")


__all__ = [
    "Backend",
    "Prediction",
    "MockPhishLLMBackend",
    "OfficialRepoBackend",
    "ReplayBackend",
    "make_backend",
]
