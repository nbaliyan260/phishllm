"""Command-line interface for the search pipeline.

Subcommands:

* ``genset``  -- generate the synthetic evaluation dataset.
* ``eval``    -- run ``evaluate(candidate, dataset)`` for a single candidate.
* ``search``  -- run the full AI-driven search loop.
* ``report``  -- render plots, tables and the one-page case study.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Sequence

from .evaluator import evaluate_candidate
from .genset import generate_dataset
from .reporting import generate_all_plots, generate_all_tables, generate_case_study
from .search.loop import SearchConfig, run_search
from .utils.logging import get_logger


_LOGGER = get_logger("cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phishllm-search",
                                     description="AI-driven configuration search for PhishLLM.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("eval", help="evaluate a single candidate config")
    p_eval.add_argument("--candidate", required=True, help="path to candidate JSON")
    p_eval.add_argument("--dataset", required=True, help="path to dataset folder")
    p_eval.add_argument("--out_dir", required=True, help="output directory")
    p_eval.add_argument("--bootstrap", type=int, default=1000)
    p_eval.add_argument("--seed", type=int, default=7)
    p_eval.set_defaults(func=_cmd_eval)

    p_search = sub.add_parser("search", help="run the AI-driven search loop")
    p_search.add_argument("--dataset", required=True)
    p_search.add_argument("--candidate_dir", required=True)
    p_search.add_argument("--out_dir", required=True)
    p_search.add_argument("--rounds", type=int, default=4)
    p_search.add_argument("--proposer", choices=["heuristic", "llm"], default="heuristic")
    p_search.add_argument("--precision_floor", type=float, default=0.95)
    p_search.add_argument("--runtime_budget_sec", type=float, default=6.0)
    p_search.add_argument("--cost_budget", type=float, default=5.0)
    p_search.add_argument("--seed", type=int, default=7)
    p_search.set_defaults(func=_cmd_search)

    p_report = sub.add_parser("report", help="render plots, tables and case study")
    p_report.add_argument("--search_dir", required=True)
    p_report.add_argument("--baseline_dir", required=False, default=None)
    p_report.add_argument("--dataset", required=False, default=None,
                          help="dataset folder, used to count samples in the case study")
    p_report.add_argument("--out_dir", required=True)
    p_report.add_argument("--precision_floor", type=float, default=0.95)
    p_report.set_defaults(func=_cmd_report)

    p_genset = sub.add_parser("genset", help="synthesise the evaluation dataset")
    p_genset.add_argument("--out_dir", required=True)
    p_genset.add_argument("--seed", type=int, default=7)
    p_genset.add_argument("--phishing_per_template", type=int, default=12)
    p_genset.add_argument("--benign_per_template", type=int, default=10)
    p_genset.set_defaults(func=_cmd_genset)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _cmd_eval(args: argparse.Namespace) -> int:
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = evaluate_candidate(candidate, Path(args.dataset),
                                bootstrap_iters=args.bootstrap, seed=args.seed)

    (out_dir / "metrics.json").write_text(json.dumps(result.metrics, indent=2), encoding="utf-8")
    (out_dir / "candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    if result.rows:
        with (out_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(result.rows[0].keys()))
            writer.writeheader()
            writer.writerows(result.rows)
    print(json.dumps(result.metrics, indent=2))
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    cfg = SearchConfig(
        dataset_dir=Path(args.dataset),
        candidate_dir=Path(args.candidate_dir),
        out_dir=Path(args.out_dir),
        rounds=int(args.rounds),
        proposer=str(args.proposer),
        precision_floor=float(args.precision_floor),
        runtime_budget_sec=float(args.runtime_budget_sec),
        cost_budget_per_1k=float(args.cost_budget),
        seed=int(args.seed),
    )
    summary = run_search(cfg)
    print(json.dumps({
        "rounds_run": summary["rounds_run"],
        "n_evaluated": len(summary["history"]),
        "top": [{"name": t["candidate"]["name"], "metrics": t["metrics"]}
                for t in summary["top"]],
    }, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    search_dir = Path(args.search_dir)
    out_dir = Path(args.out_dir)
    plot_dir = out_dir / "plots"
    table_dir = out_dir / "tables"

    written: List[Path] = []
    written += generate_all_plots(search_dir, plot_dir, args.precision_floor)
    written += generate_all_tables(
        search_dir,
        table_dir,
        baseline_dir=Path(args.baseline_dir) if args.baseline_dir else None,
        precision_floor=args.precision_floor,
    )
    if args.baseline_dir and args.dataset:
        case_path = generate_case_study(
            search_dir,
            Path(args.baseline_dir),
            Path(args.dataset),
            out_dir / "case_study.md",
            precision_floor=args.precision_floor,
        )
        written.append(case_path)

    print(json.dumps({"artifacts": [str(p) for p in written]}, indent=2))
    return 0


def _cmd_genset(args: argparse.Namespace) -> int:
    labels_path, n = generate_dataset(
        Path(args.out_dir),
        seed=args.seed,
        phishing_per_template=args.phishing_per_template,
        benign_per_template=args.benign_per_template,
    )
    print(json.dumps({"labels": str(labels_path), "n": n}, indent=2))
    return 0


def eval_main() -> None:
    sys.exit(main(["eval", *sys.argv[1:]]))


def search_main() -> None:
    sys.exit(main(["search", *sys.argv[1:]]))


def report_main() -> None:
    sys.exit(main(["report", *sys.argv[1:]]))


def genset_main() -> None:
    sys.exit(main(["genset", *sys.argv[1:]]))


if __name__ == "__main__":
    sys.exit(main())
