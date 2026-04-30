"""Deterministic candidate hashing used for de-duplication."""

from __future__ import annotations

import hashlib
import json
from typing import Dict


_IGNORED_FIELDS = {"name", "hypothesis"}


def candidate_hash(candidate: Dict) -> str:
    """Stable hash of a candidate that ignores the human-readable name.

    Two candidates with the same configuration but different names map to the
    same hash, which prevents the search loop from re-evaluating an equivalent
    configuration under a new label.
    """
    normalised = {k: v for k, v in sorted(candidate.items()) if k not in _IGNORED_FIELDS}
    blob = json.dumps(normalised, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]
