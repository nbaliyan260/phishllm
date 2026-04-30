#!/bin/bash
#SBATCH --job-name=phishllm-eval
#SBATCH --output=runs/slurm_eval_%j.out
#SBATCH --error=runs/slurm_eval_%j.err
#SBATCH --time=00:20:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G

set -euo pipefail

CANDIDATE="${CANDIDATE:-configs/candidates/seed_baseline.json}"
DATASET="${DATASET:-data}"
OUT_DIR="${OUT_DIR:-runs/slurm_eval/$(basename "${CANDIDATE}" .json)}"

source "${CONDA_BASE:-$HOME/miniconda3}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV:-phishllm-search}"

python -m phishllm_search.cli eval \
    --candidate "${CANDIDATE}" \
    --dataset "${DATASET}" \
    --out_dir "${OUT_DIR}"
