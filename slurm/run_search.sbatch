#!/bin/bash
#SBATCH --job-name=phishllm-search
#SBATCH --output=runs/slurm_search_%j.out
#SBATCH --error=runs/slurm_search_%j.err
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

set -euo pipefail

DATASET="${DATASET:-data}"
ROUNDS="${ROUNDS:-4}"
PROPOSER="${PROPOSER:-heuristic}"
SEED="${SEED:-7}"
OUT_DIR="${OUT_DIR:-runs/slurm_search}"

source "${CONDA_BASE:-$HOME/miniconda3}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV:-phishllm-search}"

python -m phishllm_search.cli search \
    --dataset "${DATASET}" \
    --candidate_dir configs/candidates \
    --out_dir "${OUT_DIR}" \
    --rounds "${ROUNDS}" \
    --proposer "${PROPOSER}" \
    --seed "${SEED}"

python -m phishllm_search.cli report \
    --search_dir "${OUT_DIR}" \
    --baseline_dir runs/baseline \
    --dataset "${DATASET}" \
    --out_dir artifacts
