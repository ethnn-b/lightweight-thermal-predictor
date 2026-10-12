#!/usr/bin/env bash
# Re-run HotSpot example1, convert outputs to CSV/plots, and copy results to the Windows project folder.
set -e
W="/mnt/c/Users/ethan/projects/Lightweight Thermal Predictor"
cd ~/projects/HotSpot/examples/example1
bash run.sh > /dev/null 2>&1
python3 "$W/analysis/analyze_example1.py" outputs
mkdir -p "$W/results/example1"
cp outputs/* ev6.flp gcc.ptrace example.config "$W/results/example1/"
ls "$W/results/example1"
