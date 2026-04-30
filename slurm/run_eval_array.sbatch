#!/bin/bash
#SBATCH --job-name=phishllm-eval-array
#SBATCH --output=runs/slurm_eval_%A_%a.out
#SBATCH --error=runs/slurm_eval_%A_%a.err
#SBATCH --time=00:20:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --array=0-7
#
# Submit one task per candidate JSON in configs/candidates/.
# Override DATASET / OUT_DIR via --export when submitting:
#   sbatch --export=DATASET=data,OUT_DIR=runs/array slurm/run_eval_array.sbatch

set -euo pipefail

DATASET="${DATASET:-data}"
OUT_DIR="${OUT_DIR:-runs/slurm_eval_array}"
mapfile -t CANDIDATES < <(ls configs/candidates/*.json | sort)

CAND="${CANDIDATES[$SLURM_ARRAY_TASK_ID]}"
NAME="$(basename "${CAND}" .json)"

source "${CONDA_BASE:-$HOME/miniconda3}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV:-phishllm-search}"

python -m phishllm_search.cli eval \
    --candidate "${CAND}" \
    --dataset "${DATASET}" \
    --out_dir "${OUT_DIR}/${NAME}"
