"""Stage 3 report versions of the Pareto figures (larger, no overlapping labels).

Reads the points written by run.py. Transient panel: T1, T3 and the cores-only ARX models (the
all-blocks ARX variants and T4 are left out). Steady panel: the S2 and S2-lr families are drawn
as connected series with one label each, S0 and S1 are labelled individually.

    python3 experiments/P3-3_pareto/report_figs.py
"""
import csv

import numpy as np

from common import results_dir, plt

OUT = results_dir(__file__)
plt.rcParams.update({"font.size": 10})


def read(name):
    with open(OUT / name) as f:
        return [dict(r, size_bytes=float(r["size_bytes"]), error_K=max(float(r["error_K"]), 1e-7),
                     time_us=float(r["time_us"])) for r in csv.DictReader(f)]


def pareto(group):
    pts = [(g["size_bytes"], g["error_K"]) for g in group]
    return [g for g, (s, e) in zip(group, pts)
            if not any(s2 <= s and e2 <= e and (s2 < s or e2 < e) for s2, e2 in pts)]


def base(ax, group, title, vmin, vmax):
    sc = ax.scatter([g["size_bytes"] for g in group], [g["error_K"] for g in group],
                    c=[g["time_us"] for g in group], cmap="viridis", vmin=vmin, vmax=vmax,
                    s=55, zorder=3, edgecolors="k", linewidths=0.4)
    front = sorted((g["size_bytes"], g["error_K"]) for g in pareto(group))
    ax.plot(*zip(*front), "r--", lw=1.0, zorder=2, label="Pareto front")
    ax.set(xscale="log", yscale="log", xlabel="model size (bytes of coefficients)",
           ylabel="worst error over cores (K)", title=title)
    return sc


def label(ax, g, text, dx, dy, ha="left", bold=False):
    ax.annotate(text, (g["size_bytes"], g["error_K"]), xytext=(dx, dy), textcoords="offset points",
                ha=ha, va="center", fontsize=9, weight="bold" if bold else "normal")


def transient():
    pts = [g for g in read("transient_points.csv")
           if g["model"] == "T1" or g["model"].startswith("T3") or g["model"].endswith("cores only")]
    on_front = {g["model"] for g in pareto(pts)}
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    sc = base(ax, pts, "Transient models (10 s test traces)", 1.5, 7.6)
    offsets = {"T1": (8, 4, "left"), "T3 M=2": (8, 6, "left"), "T3 M=3": (8, 8, "left"),
               "T3 M=4": (8, 0, "left"), "T3 M=5": (8, 0, "left"), "T3 M=6": (8, 0, "left"),
               "T2 ARX(1,1) cores only": (8, -9, "left"),
               "T2 ARX(2,2) cores only": (-8, -4, "right"),
               "T2 ARX(3,3) cores only": (-8, -6, "right")}
    for g in pts:
        dx, dy, ha = offsets[g["model"]]
        text = g["model"].replace(" cores only", "")
        label(ax, g, text, dx, dy, ha, g["model"] in on_front)
    ax.set_xlim(500, 9000); ax.set_ylim(0.04, 30)
    fig.colorbar(sc, ax=ax, label="time per step (µs)")
    ax.legend(loc="lower left", fontsize=9)
    fig.savefig(OUT / "pareto_transient_report.png", dpi=150)


def steady():
    pts = read("steady_points.csv")
    fig, ax = plt.subplots(figsize=(7.5, 4.3))
    sc = base(ax, pts, "Steady models (24 floorplans)", 1.6, 3.9)
    for prefix, text, colour in (("S2 k=", "S2, k = 0–5", "C0"), ("S2-lr r=", "S2-lr, r = 1–8", "C1")):
        fam = sorted((g for g in pts if g["model"].startswith(prefix)), key=lambda g: g["size_bytes"])
        ax.plot([g["size_bytes"] for g in fam], [g["error_K"] for g in fam], "-", c=colour, lw=0.9,
                zorder=1, label=text)
    one = {g["model"]: g for g in pts}
    label(ax, one["S0 power blurring"], "S0 power blurring", 8, 6)
    label(ax, one["S1 float32"], "S1 (32-bit)", -8, 10, "right", True)
    label(ax, one["S1 influence matrix"], "S1 (64-bit)", 8, 10, "left", True)
    ax.set_xlim(150, 2000); ax.set_ylim(1e-5, 40)
    fig.colorbar(sc, ax=ax, label="time per call (µs)")
    ax.legend(loc="center right", fontsize=9)
    fig.savefig(OUT / "pareto_steady_report.png", dpi=150)


if __name__ == "__main__":
    transient()
    steady()
