#!/usr/bin/env bash
# Run one experiment inside WSL and keep a log next to its results.
#   usage:  bash experiments/run.sh P0-2_linearity
set -euo pipefail
cd "$(dirname "$0")/.."
exp=$1
mkdir -p "experiments/$exp/results"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$PWD:$PWD/experiments" python3 "experiments/$exp/run.py" "${@:2}" 2>&1 \
  | tee "experiments/$exp/results/log.txt"
