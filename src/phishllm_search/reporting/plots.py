"""Matplotlib plots used by the final report.

All plots are rendered with the default matplotlib style, no seaborn, no
custom colours per the project conventions. Each helper writes a PNG and a
PDF copy to the output directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")  # headless / CI-safe
import matplotlib.pyplot as plt
import pandas as pd


def _save(fig, out_dir: Path, stem: str) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for ext in ("png", "pdf"):
        path = out_dir / f"{stem}.{ext}"
        fig.savefig(path, bbox_inches="tight", dpi=150)
        paths.append(path)
    plt.close(fig)
    return paths


def _load_history(search_dir: Path) -> pd.DataFrame:
    csv_path = search_dir / "search_summary.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No search_summary.csv at {csv_path}")
    df = pd.read_csv(csv_path)
    return df


def plot_search_trace(search_dir: Path, out_dir: Path, precision_floor: float = 0.95) -> List[Path]:
    """Best-recall-so-far over rounds, with the precision floor highlighted."""
    df = _load_history(search_dir)
    df = df.sort_values(["round", "name"])

    eligible = df[df["precision"] >= precision_floor].copy()
    rounds = sorted(df["round"].unique())
    best_so_far: List[float] = []
    running = 0.0
    for r in rounds:
        round_best = eligible[eligible["round"] <= r]["recall"].max()
        running = max(running, float(round_best) if pd.notna(round_best) else running)
        best_so_far.append(running)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(rounds, best_so_far, marker="o", linewidth=2)
    for r in rounds:
        round_df = df[df["round"] == r]
        ax.scatter(
            [r] * len(round_df), round_df["recall"],
            alpha=0.4, s=24, edgecolors="none",
        )
    ax.set_xlabel("Search round")
    ax.set_ylabel("Recall (precision >= %.2f)" % precision_floor)
    ax.set_title("Search trace: best-recall-so-far under precision floor")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.02)
    return _save(fig, out_dir, "search_trace_recall")


def plot_pareto(search_dir: Path, out_dir: Path, precision_floor: float = 0.95) -> List[Path]:
    """Recall vs runtime, highlighting the Pareto frontier."""
    df = _load_history(search_dir)
    df = df[df["precision"] >= precision_floor].copy()
    if df.empty:
        return []

    df = df.sort_values("median_runtime_sec")
    is_frontier: List[bool] = []
    best_recall = -1.0
    for _, row in df.iterrows():
        if row["recall"] > best_recall:
            is_frontier.append(True)
            best_recall = float(row["recall"])
        else:
            is_frontier.append(False)
    df["is_frontier"] = is_frontier

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(df["median_runtime_sec"], df["recall"], s=40, alpha=0.5, label="evaluated")
    front = df[df["is_frontier"]]
    ax.plot(front["median_runtime_sec"], front["recall"], color="black",
            linewidth=2, marker="s", markersize=6, label="Pareto frontier")
    for _, row in front.iterrows():
        ax.annotate(row["name"], (row["median_runtime_sec"], row["recall"]),
                    fontsize=7, alpha=0.8, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Median runtime per page (seconds)")
    ax.set_ylabel("Recall (under precision floor)")
    ax.set_title("Pareto frontier: recall vs runtime")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower right")
    return _save(fig, out_dir, "pareto_recall_vs_runtime")


def plot_failure_buckets(search_dir: Path, out_dir: Path) -> List[Path]:
    """Stacked bar of failure-bucket counts per round, summed over candidates."""
    df = _load_history(search_dir)
    bucket_cols = [c for c in df.columns if c.startswith("failures.")]
    if not bucket_cols:
        return []

    by_round = df.groupby("round")[bucket_cols].sum()
    by_round.columns = [c.replace("failures.", "") for c in by_round.columns]

    fig, ax = plt.subplots(figsize=(6, 4))
    by_round.plot(kind="bar", stacked=True, ax=ax, width=0.85)
    ax.set_xlabel("Search round")
    ax.set_ylabel("Failures (sum across candidates)")
    ax.set_title("Failure buckets per round")
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend(loc="upper right", fontsize=8, ncols=2)
    return _save(fig, out_dir, "failure_buckets_per_round")


def plot_top_confusion(search_dir: Path, out_dir: Path) -> List[Path]:
    """Confusion-matrix heatmap of the best candidate."""
    top5_path = search_dir / "top5.json"
    if not top5_path.exists():
        return []
    top = json.loads(top5_path.read_text(encoding="utf-8"))
    if not top:
        return []
    cm = top[0]["metrics"].get("confusion")
    if not cm:
        return []
    labels = ("benign", "phish")
    matrix = [[cm[y][p] for p in labels] for y in labels]
    fig, ax = plt.subplots(figsize=(4, 4))
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(2)); ax.set_xticklabels([f"pred={p}" for p in labels])
    ax.set_yticks(range(2)); ax.set_yticklabels([f"true={y}" for y in labels])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(matrix[i][j]), ha="center", va="center",
                    color="white" if matrix[i][j] > max(max(matrix)) / 2 else "black",
                    fontsize=12, fontweight="bold")
    ax.set_title(f"Confusion: {top[0]['name']}")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    return _save(fig, out_dir, "top_confusion_matrix")


def plot_recall_with_ci(search_dir: Path, out_dir: Path, top_k: int = 6) -> List[Path]:
    """Bar chart of top-K recall with bootstrap CI error bars."""
    df = _load_history(search_dir)
    if df.empty:
        return []
    eligible = df[df["precision"] >= 0.95].copy()
    src = eligible if not eligible.empty else df
    src = src.sort_values("recall", ascending=False).head(top_k)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    x = range(len(src))
    yerr_lo = src["recall"].values - src["recall_ci_lo"].values
    yerr_hi = src["recall_ci_hi"].values - src["recall"].values
    ax.bar(x, src["recall"], yerr=[yerr_lo, yerr_hi], capsize=4, alpha=0.85)
    ax.set_xticks(list(x))
    ax.set_xticklabels(src["name"], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Recall (95% bootstrap CI)")
    ax.set_title("Top candidates: recall with bootstrap CI")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3, axis="y")
    return _save(fig, out_dir, "topk_recall_ci")


def generate_all_plots(search_dir: Path, out_dir: Path, precision_floor: float = 0.95) -> List[Path]:
    """Render every plot used by the final report."""
    out_dir = Path(out_dir)
    written: List[Path] = []
    for fn in (
        lambda: plot_search_trace(search_dir, out_dir, precision_floor),
        lambda: plot_pareto(search_dir, out_dir, precision_floor),
        lambda: plot_failure_buckets(search_dir, out_dir),
        lambda: plot_top_confusion(search_dir, out_dir),
        lambda: plot_recall_with_ci(search_dir, out_dir),
    ):
        written.extend(fn())
    return written
