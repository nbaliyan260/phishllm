"""Lightweight, dependency-free structured logging for the search loop."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


_LOGGER_NAME = "phishllm_search"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a configured logger.

    The first call configures the root package logger to emit human-readable
    INFO lines on stderr. Subsequent calls return a child logger.
    """
    root = logging.getLogger(_LOGGER_NAME)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s",
                                               datefmt="%H:%M:%S"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
    return root if name is None else root.getChild(name)


class JsonlWriter:
    """Append-only JSONL writer used to persist structured search events.

    Files written by this class are intended to be consumed by the reporting
    pipeline (``reporting.plots`` / ``reporting.tables``).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open("a", encoding="utf-8")

    def write(self, event: Dict[str, Any]) -> None:
        record = {"ts": time.time(), **event}
        self._fp.write(json.dumps(record, sort_keys=True) + "\n")
        self._fp.flush()

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:  # pragma: no cover - close is best-effort
            pass

    def __enter__(self) -> "JsonlWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
