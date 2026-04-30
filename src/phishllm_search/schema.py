"""Candidate-config validation and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from jsonschema import Draft202012Validator, ValidationError


_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "configs" / "schema" / "candidate.schema.json"
)


def _load_schema() -> Dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


_SCHEMA = _load_schema()
_VALIDATOR = Draft202012Validator(_SCHEMA)


class CandidateValidationError(ValueError):
    """Raised when a candidate does not match the JSON schema."""


def schema() -> Dict[str, Any]:
    """Return a deep-copyable view of the candidate schema."""
    return json.loads(json.dumps(_SCHEMA))


def schema_summary() -> str:
    """Compact human-readable schema summary used in proposer prompts."""
    props = _SCHEMA["properties"]
    lines: List[str] = []
    for key in _SCHEMA["required"]:
        spec = props[key]
        if "enum" in spec:
            lines.append(f"  {key}: one of {spec['enum']}")
        elif spec.get("type") == "boolean":
            lines.append(f"  {key}: true | false")
        elif spec.get("type") in {"number", "integer"}:
            lo, hi = spec.get("minimum"), spec.get("maximum")
            lines.append(f"  {key}: {spec['type']} in [{lo}, {hi}]")
        else:
            lines.append(f"  {key}: {spec.get('type', 'any')}")
    return "\n".join(lines)


def validate(candidate: Dict[str, Any]) -> None:
    """Raise :class:`CandidateValidationError` if ``candidate`` is invalid."""
    errors: List[ValidationError] = sorted(_VALIDATOR.iter_errors(candidate), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors)
        raise CandidateValidationError(msg)


def is_valid(candidate: Dict[str, Any]) -> bool:
    return _VALIDATOR.is_valid(candidate)


def validate_many(candidates: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Partition candidates into ``(valid, errors)``.

    ``errors`` contains the human-readable error message for each rejected
    candidate, in input order.
    """
    valid: List[Dict[str, Any]] = []
    errors: List[str] = []
    for cand in candidates:
        try:
            validate(cand)
        except CandidateValidationError as exc:
            errors.append(str(exc))
            continue
        valid.append(cand)
    return valid, errors
