"""P1-3 extra figure: error of a borrowed influence matrix against what it costs to get G.

Reads results/all_results.csv (no HotSpot runs). A borrowed G (c1, c2) and S0 need no HotSpot run
on the target floorplan; S1 needs 8 steady runs (4.3 s, P1-1). All four predict with the same
matrix-vector product, so prediction time is the same (2.6 us for S1, P2-1) and is not an axis.

    python3 experiments/P1-3_is_calibration_needed/plot_borrowed_g.py
"""
import csv

import numpy as np

from common import results_dir, plt

OUT = results_dir(__file__)

# (method name in all_results.csv, label, x position, colour)
SERIES = [("(c1) transfer within Style_4", "borrow G from\nanother Style_4\nfloorplan (c1)\n\n0 HotSpot runs", 0, "#d95f02"),
          ("(c2) transfer from s1_fp001", "borrow G from\ns1_fp001 (c2)\n\n\n0 HotSpot runs", 1.5, "#7570b3"),
          ("(a) S0 power blurring", "S0 power blurring\n(generic kernel)\n\n\n0 HotSpot runs", 3, "#999999"),
          ("S1 calibrated", "S1 calibrated\non the target\n\n\n8 steady runs, 4.3 s", 5, "#1b9e77")]


def main():
    rows = list(csv.DictReader(open(OUT / "all_results.csv")))
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(1, 2, figsize=(11, 5))
    for a, key, title in zip(ax, ("mae_K", "max_K"),
                             ("mean abs error per floorplan", "worst error per floorplan")):
        for name, label, x, col in SERIES:
            v = np.array([float(r[key]) for r in rows if r["method"] == name])
            a.scatter(x + rng.uniform(-0.18, 0.18, len(v)), v, s=14, color=col, alpha=0.55, lw=0)
            a.hlines(np.median(v), x - 0.3, x + 0.3, color="k", lw=1.6)
            a.annotate(f"{np.median(v):.2g}", (x + 0.32, np.median(v)), fontsize=8, va="center")
        a.set_yscale("log")
        a.set_xticks([s[2] for s in SERIES], [s[1] for s in SERIES], fontsize=7)
        a.set(ylabel="error vs HotSpot (K)", title=title)
        a.grid(axis="y", alpha=0.3)
        a.axvline(4.0, color="k", ls=":", lw=0.8)
    fig.suptitle("Borrowing a G is free but 1-12 K wrong; calibrating costs 4 s and is exact\n"
                 "(all four predict in the same ~2.6 µs: one matrix-vector product; black bar = median)",
                 fontsize=9)
    fig.subplots_adjust(top=0.84, bottom=0.25, wspace=0.25)
    fig.savefig(OUT / "borrowed_g_error_vs_cost.png")

    # the numbers behind the figure
    out = []
    for name, label, x, _ in SERIES:
        for key in ("mae_K", "max_K"):
            v = np.array([float(r[key]) for r in rows if r["method"] == name])
            out.append(dict(method=name, hotspot_runs=8 if x == 5 else 0, metric=key, n=len(v),
                            median=float(np.median(v)), worst=float(v.max())))
    with open(OUT / "borrowed_g_error_vs_cost.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader(); w.writerows(out)
    for r in out:
        print(r)


if __name__ == "__main__":
    main()
