"""Thin shell-out wrapper around the official PhishLLM repository.

This backend is deliberately minimal: it serialises the candidate as JSON and
hands it to a user-supplied shell command that must (a) run the official
inference for the given site, (b) print a single-line JSON object on the last
line of stdout containing the same fields as :class:`Prediction`.

The wrapper does no parsing of the official repo's internal logs; this keeps
the contract between our search loop and the upstream code minimal and
auditable. See ``docs/connecting_to_official_repo.md`` for an example shell
command and a worked example of the expected stdout payload.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict

from ..dataset import Sample
from .base import Backend, Prediction


class OfficialRepoBackend(Backend):
    def __init__(self, repo_root: str | Path, python_executable: str = "python") -> None:
        self.repo_root = Path(repo_root)
        self.python_executable = python_executable

    def predict(self, sample: Sample, candidate: Dict) -> Prediction:
        command = candidate.get("official_repo_command")
        if not command:
            raise RuntimeError(
                "official_repo_command missing in candidate. Provide a shell "
                "command that runs official PhishLLM inference and prints a "
                "single-line JSON prediction on its last stdout line."
            )

        env = os.environ.copy()
        env["PHISHLLM_CANDIDATE_JSON"] = json.dumps(candidate)
        env["PHISHLLM_URL"] = sample.url
        env["PHISHLLM_SITE_ID"] = sample.site_id
        if sample.shot_path is not None:
            env["PHISHLLM_SHOT"] = str(sample.shot_path)

        result = subprocess.run(
            command,
            shell=True,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Official repo command failed for {sample.site_id} "
                f"(exit={result.returncode}): {result.stderr.strip()}"
            )

        last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Could not parse official repo output for {sample.site_id}: {exc}\n"
                f"STDOUT={result.stdout!r}"
            ) from exc

        return Prediction(
            pred_label=payload["pred_label"],
            pred_brand=payload.get("pred_brand"),
            brand_confidence=float(payload.get("brand_confidence", 0.0)),
            brand_source=str(payload.get("brand_source", "official")),
            crp=bool(payload.get("crp", False)),
            crp_reason=str(payload.get("crp_reason", "")),
            reasons=list(payload.get("reasons", [])),
            runtime_sec=float(payload.get("runtime_sec", 0.0)),
            estimated_cost=float(payload.get("estimated_cost", 0.0)),
        )
