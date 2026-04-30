"""Backend protocol and prediction dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from ..dataset import Sample


@dataclass
class Prediction:
    """A single per-sample prediction from any backend."""

    pred_label: str                         # "phish" | "benign"
    pred_brand: Optional[str]               # registered domain or None
    brand_confidence: float                 # in [0.0, 1.0]
    brand_source: str                       # "ocr+caption" | "single_modality" | ...
    crp: bool                               # ground-truth-style boolean
    crp_reason: str
    reasons: List[str] = field(default_factory=list)
    runtime_sec: float = 0.0
    estimated_cost: float = 0.0             # USD-equivalent per page

    def to_dict(self) -> Dict[str, object]:
        return {
            "pred_label": self.pred_label,
            "pred_brand": self.pred_brand,
            "brand_confidence": round(self.brand_confidence, 4),
            "brand_source": self.brand_source,
            "crp": self.crp,
            "crp_reason": self.crp_reason,
            "reasons": list(self.reasons),
            "runtime_sec": round(self.runtime_sec, 4),
            "estimated_cost": round(self.estimated_cost, 6),
        }


class Backend(Protocol):
    """Anything that can turn ``(sample, candidate)`` into a :class:`Prediction`."""

    def predict(self, sample: Sample, candidate: Dict) -> Prediction:  # pragma: no cover - protocol
        ...
