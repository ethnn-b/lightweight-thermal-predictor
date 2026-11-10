"""P2-1 figure for the Stage 2 report: worst error per floorplan of S0 and S1 only.

Reads results/all_results.csv (no HotSpot runs).

    python experiments/P2-1_steady_predictor/plot_stage2.py
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import plt  # noqa: E402

OUT = HERE / "results"
MODELS = [("S0 power blurring", "S0\n(uncalibrated)"), ("S1 influence matrix", "S1\n(calibrated)")]


def main():
    rows = list(csv.DictReader(open(OUT / "all_results.csv")))
    data = [[float(r["max_K"]) for r in rows if r["model"] == m] for m, _ in MODELS]
    fig, ax = plt.subplots(figsize=(4.5, 3.4))
    ax.boxplot(data)
    ax.set_yscale("log")
    ax.set_xticks([1, 2], [lab for _, lab in MODELS])
    ax.set(ylabel="worst abs error per floorplan (K)", title="24 floorplans, 302 test vectors each")
    fig.savefig(OUT / "steady_accuracy_stage2.png", dpi=200)
    for (m, _), d in zip(MODELS, data):
        print(f"{m}: n={len(d)} median={sorted(d)[len(d) // 2]:.3g} worst={max(d):.3g}")


if __name__ == "__main__":
    main()
