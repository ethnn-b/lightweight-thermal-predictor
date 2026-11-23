#!/usr/bin/env bash
# Re-run HotSpot example1, convert outputs to CSV/plots, and copy results to the Windows project folder.
set -e
W="$(cd "$(dirname "$0")/../.." && pwd)"   # the repository root, wherever it is
cd ~/projects/HotSpot/examples/example1
bash run.sh > /dev/null 2>&1
python3 "$W/setup/example1/analyze_example1.py" outputs
mkdir -p "$W/setup/example1/results"
cp outputs/* ev6.flp gcc.ptrace example.config "$W/setup/example1/results/"
ls "$W/setup/example1/results"
