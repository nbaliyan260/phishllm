"""Dataset loader for the per-site folder layout used by PhishLLM.

Each sample lives in ``<root>/<site_id>/`` and contains:

- ``info.txt``  - the URL on a single line
- ``html.txt``  - the rendered HTML / extracted text
- ``shot.png``  - optional screenshot (not required by the mock backend)

Ground-truth labels and metadata are read from ``<root>/labels.csv`` with
columns ``site_id, label, target_brand, is_crp, notes``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Sample:
    """A single labelled webpage sample."""

    site_id: str
    url: str
    html: str
    label: str            # "phish" | "benign"
    target_brand: str
    is_crp: int           # 0 / 1 ground truth
    notes: str
    shot_path: Optional[Path] = None


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_samples(dataset_dir: Path) -> List[Sample]:
    """Load all labelled samples from ``dataset_dir``.

    Raises ``FileNotFoundError`` if the labels CSV or any per-site file is
    missing; this is intentional - silently dropping samples would break
    reproducibility guarantees.
    """
    dataset_dir = Path(dataset_dir)
    labels_path = dataset_dir / "labels.csv"
    if not labels_path.exists():
        raise FileNotFoundError(f"Missing labels.csv at {labels_path}")

    samples: List[Sample] = []
    with labels_path.open("r", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        required = {"site_id", "label"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"labels.csv missing columns: {sorted(missing)}")

        for row in reader:
            site_id = row["site_id"].strip()
            site_dir = dataset_dir / site_id
            url = _read_text(site_dir / "info.txt")
            html = _read_text(site_dir / "html.txt")
            shot = site_dir / "shot.png"
            samples.append(
                Sample(
                    site_id=site_id,
                    url=url,
                    html=html,
                    label=row["label"].strip(),
                    target_brand=(row.get("target_brand") or "").strip(),
                    is_crp=int(row.get("is_crp") or 0),
                    notes=(row.get("notes") or "").strip(),
                    shot_path=shot if shot.exists() else None,
                )
            )

    if not samples:
        raise ValueError(f"No samples loaded from {dataset_dir}")
    return samples


def stratified_split(samples: List[Sample], seed: int = 0, ratio: float = 0.5) -> tuple[List[Sample], List[Sample]]:
    """Deterministic stratified split useful for held-out validation.

    Not used by the default evaluator (which evaluates on the full set), but
    handy for ablations and the bootstrap utilities in :mod:`evaluator.metrics`.
    """
    import random

    rng = random.Random(seed)
    by_label: dict[str, List[Sample]] = {}
    for s in samples:
        by_label.setdefault(s.label, []).append(s)
    a: List[Sample] = []
    b: List[Sample] = []
    for label, group in by_label.items():
        ordered = sorted(group, key=lambda s: s.site_id)
        rng.shuffle(ordered)
        cut = int(len(ordered) * ratio)
        a.extend(ordered[:cut])
        b.extend(ordered[cut:])
    a.sort(key=lambda s: s.site_id)
    b.sort(key=lambda s: s.site_id)
    return a, b
