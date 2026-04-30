"""Replay backend: serves cached predictions to make search loops cheap."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ..dataset import Sample
from .base import Backend, Prediction


class ReplayBackend(Backend):
    """Read pre-computed predictions from ``<replay_dir>/<site_id>.json``."""

    def __init__(self, replay_dir: str | Path) -> None:
        self.replay_dir = Path(replay_dir)
        if not self.replay_dir.is_dir():
            raise FileNotFoundError(f"replay_dir does not exist: {self.replay_dir}")

    def predict(self, sample: Sample, candidate: Dict) -> Prediction:
        path = self.replay_dir / f"{sample.site_id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No cached prediction at {path} (replay backend strict mode)."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Prediction(
            pred_label=payload["pred_label"],
            pred_brand=payload.get("pred_brand"),
            brand_confidence=float(payload.get("brand_confidence", 0.0)),
            brand_source=str(payload.get("brand_source", "replay")),
            crp=bool(payload.get("crp", False)),
            crp_reason=str(payload.get("crp_reason", "")),
            reasons=list(payload.get("reasons", [])),
            runtime_sec=float(payload.get("runtime_sec", 0.0)),
            estimated_cost=float(payload.get("estimated_cost", 0.0)),
        )
