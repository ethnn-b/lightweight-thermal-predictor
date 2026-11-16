"""Extended validation figure for the Stage 3 report: T3's mean error per generated floorplan,
grouped by style (the T3 half of error_by_style.png, without the S1 panel).

Reads results/all_results.csv (no HotSpot runs).

    PYTHONPATH="$PWD:$PWD/experiments" python3 experiments/extended_validation/plot_stage3.py
"""
import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import plt  # noqa: E402

OUT = HERE / "results"
REF_T3_MAE_K = 0.090                      # main set, as in run.py


def main():
    rows = list(csv.DictReader(open(OUT / "all_results.csv")))
    styles = sorted({r["style"] for r in rows})
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(figsize=(6, 3.8))
    for i, s in enumerate(styles):
        v = np.array([float(r["t3_mae_K"]) for r in rows if r["style"] == s])
        ax.scatter(i + rng.uniform(-0.15, 0.15, len(v)), v, s=16, alpha=0.7, lw=0)
        ax.hlines(np.median(v), i - 0.3, i + 0.3, color="k", lw=1.5)
    ax.axhline(REF_T3_MAE_K, color="r", ls="--", lw=1, label=f"main set: {REF_T3_MAE_K:g} K")
    ax.set_yscale("log")
    ax.set_xticks(range(len(styles)), [s.replace("_", " ") for s in styles])
    ax.set(ylabel="T3 mean error vs HotSpot (K)", title="T3 (M = 4), 2 s test trace")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.savefig(OUT / "error_by_style_t3.png")


if __name__ == "__main__":
    main()
