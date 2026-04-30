"""Generate Markdown / CSV summary tables from the search outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


_COLS = ("name", "round", "precision", "recall", "f1", "fpr", "fnr",
        "median_runtime_sec", "p95_runtime_sec", "estimated_cost_per_1k",
        "tp", "fp", "tn", "fn")


def leaderboard(search_dir: Path, out_dir: Path, precision_floor: float = 0.95) -> List[Path]:
    """Top-10 leaderboard ranked by the precision-floor selector key."""
    csv_path = search_dir / "search_summary.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    df["respects_floor"] = df["precision"] >= precision_floor
    df = df.sort_values(
        ["respects_floor", "recall", "f1", "median_runtime_sec", "estimated_cost_per_1k"],
        ascending=[False, False, False, True, True],
    )
    top = df[list(_COLS)].head(10)

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out = out_dir / "leaderboard_top10.csv"
    md_out = out_dir / "leaderboard_top10.md"
    top.to_csv(csv_out, index=False, float_format="%.4f")
    md_out.write_text(_to_markdown(top), encoding="utf-8")
    return [csv_out, md_out]


def failure_summary(search_dir: Path, out_dir: Path) -> List[Path]:
    csv_path = search_dir / "search_summary.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    bucket_cols = [c for c in df.columns if c.startswith("failures.")]
    if not bucket_cols:
        return []
    by_round = df.groupby("round")[bucket_cols].sum()
    by_round.columns = [c.replace("failures.", "") for c in by_round.columns]

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out = out_dir / "failures_per_round.csv"
    md_out = out_dir / "failures_per_round.md"
    by_round.to_csv(csv_out)
    md_out.write_text(_to_markdown(by_round.reset_index()), encoding="utf-8")
    return [csv_out, md_out]


def baseline_vs_best(search_dir: Path, baseline_dir: Path, out_dir: Path) -> List[Path]:
    """Side-by-side comparison of the baseline and the search-best candidate."""
    bm_path = baseline_dir / "metrics.json"
    top_path = search_dir / "top5.json"
    if not bm_path.exists() or not top_path.exists():
        return []
    baseline = json.loads(bm_path.read_text(encoding="utf-8"))
    top5 = json.loads(top_path.read_text(encoding="utf-8"))
    if not top5:
        return []
    best = top5[0]["metrics"]

    rows = [
        {"metric": "candidate", "baseline": baseline.get("candidate_name"), "best": best.get("candidate_name")},
        {"metric": "precision", "baseline": baseline.get("precision"), "best": best.get("precision")},
        {"metric": "recall", "baseline": baseline.get("recall"), "best": best.get("recall")},
        {"metric": "F1", "baseline": baseline.get("f1"), "best": best.get("f1")},
        {"metric": "FPR", "baseline": baseline.get("fpr"), "best": best.get("fpr")},
        {"metric": "FNR", "baseline": baseline.get("fnr"), "best": best.get("fnr")},
        {"metric": "median runtime (s)", "baseline": baseline.get("median_runtime_sec"), "best": best.get("median_runtime_sec")},
        {"metric": "cost / 1K pages",   "baseline": baseline.get("estimated_cost_per_1k"), "best": best.get("estimated_cost_per_1k")},
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out = out_dir / "baseline_vs_best.csv"
    md_out = out_dir / "baseline_vs_best.md"
    with csv_out.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["metric", "baseline", "best"])
        writer.writeheader()
        writer.writerows(rows)
    md_out.write_text(_to_markdown(pd.DataFrame(rows)), encoding="utf-8")
    return [csv_out, md_out]


def per_seed_summary(search_dir: Path, out_dir: Path) -> List[Path]:
    """Round-0 (seed) metrics in a clean table."""
    csv_path = search_dir / "search_summary.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    seeds = df[df["round"] == 0][list(_COLS)]
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out = out_dir / "seeds_round0.csv"
    md_out = out_dir / "seeds_round0.md"
    seeds.to_csv(csv_out, index=False, float_format="%.4f")
    md_out.write_text(_to_markdown(seeds), encoding="utf-8")
    return [csv_out, md_out]


def generate_all_tables(
    search_dir: Path,
    out_dir: Path,
    baseline_dir: Path | None = None,
    precision_floor: float = 0.95,
) -> List[Path]:
    out_dir = Path(out_dir)
    written: List[Path] = []
    written += leaderboard(search_dir, out_dir, precision_floor)
    written += failure_summary(search_dir, out_dir)
    written += per_seed_summary(search_dir, out_dir)
    if baseline_dir is not None:
        written += baseline_vs_best(search_dir, baseline_dir, out_dir)
    return written


def _to_markdown(df: pd.DataFrame) -> str:
    """Tiny markdown-table renderer (avoids the optional ``tabulate`` dep)."""
    if df.empty:
        return "_(empty)_\n"
    cols = list(df.columns)
    header = "| " + " | ".join(map(str, cols)) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body_rows: List[str] = []
    for _, row in df.iterrows():
        cells: List[str] = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        body_rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *body_rows]) + "\n"
