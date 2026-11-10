"""P1-3 figure for the Stage 2 report: only the methods the report keeps.

Reads results/all_results.csv (no HotSpot runs) and plots the per-floorplan mean abs error of
  - S1 calibrated (8 runs on the target),
  - S0 power blurring,
  - G borrowed from another floorplan of the same style (c1: all 90 Style_4 pairs),
  - G borrowed from another style (c2: s1_fp001's G applied to the 20 non-Style_1 floorplans).
The learned methods (b), (d), (d2), (d3) are left out. Also prints the table numbers.

    python experiments/P1-3_is_calibration_needed/plot_stage2.py
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent / "results"

SERIES = [
    ("S1 calibrated", None, "S1\ncalibrated"),
    ("(a) S0 power blurring", None, "S0 power\nblurring"),
    ("(c1) transfer within Style_4", None, "borrow G,\nsame style"),
    ("(c2) transfer from s1_fp001", lambda r: r["style"] != "Style_1", "borrow G,\nanother style"),
]


def main():
    rows = list(csv.DictReader(open(OUT / "all_results.csv")))
    data = []
    for meth, keep, label in SERIES:
        rr = [r for r in rows if r["method"] == meth and (keep is None or keep(r))]
        mae = np.array([float(r["mae_K"]) for r in rr])
        mx = np.array([float(r["max_K"]) for r in rr])
        acc = np.array([float(r["hottest_acc"]) for r in rr])
        print(f"{label.replace(chr(10), ' '):28s} n={len(rr):3d}  mean={mae.mean():.6g} K  "
              f"worst={mx.max():.3g} K  hottest right={100 * acc.mean():.0f} %")
        data.append(mae)

    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.boxplot(data, showfliers=True)
    ax.set_yscale("log")
    ax.set_xticks(range(1, len(SERIES) + 1), [s[2] for s in SERIES], fontsize=8)
    ax.set(ylabel="mean abs error over cores (K)\nper floorplan",
           title="steady error without per-floorplan calibration vs S1")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "error_by_method_stage2.png", dpi=200)


if __name__ == "__main__":
    main()
