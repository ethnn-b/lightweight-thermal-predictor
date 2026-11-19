#!/usr/bin/env bash
# Live demo of the predictor on a brand-new floorplan and brand-new power (see run_demo.py).
#   usage (inside WSL, from anywhere):  bash demo/run_demo.sh [--style 1-4] [--seed N] [--steps N]
# Results: demo/output/<floorplan>/  (open it from Windows Explorer)
set -euo pipefail
cd "$(dirname "$0")/.."
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$PWD"
python3 demo/run_demo.py "$@"
