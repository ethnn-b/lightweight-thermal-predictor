"""P3-3: accuracy vs model size vs prediction time (the three required metrics in one figure).

No new runs: collects the per-model results of P2-1 (steady), P3-1 (transient, long traces) and
P1-2 (ARX orders and states) and plots error against model size, coloured by prediction time.
Also marks the Pareto-optimal models (no other model is both smaller and more accurate).
"""
import csv
import json
from pathlib import Path

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt

OUT = results_dir(__file__)
EXP = Path(__file__).resolve().parents[1]


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def pareto(points):
    """Indices of points not dominated in (size, error)."""
    keep = []
    for i, (s, e) in enumerate(points):
        if not any((s2 <= s and e2 <= e) and (s2 < s or e2 < e) for s2, e2 in points):
            keep.append(i)
    return keep


def main():
    trans = []
    for r in read(EXP / "P3-1_transient_predictor" / "results" / "summary.csv"):
        if r["test"] == "long":
            trans.append(dict(model=r["model"], size_bytes=float(r["size_bytes"]),
                              error_K=float(r["max_K_worst"]), mae_K=float(r["mae_K_mean"]),
                              time_us=float(r["time_us_per_step"])))
    arx = [r for r in read(EXP / "P1-2_trace_calibration" / "results" / "summary.csv")
           if r["order"].startswith("(") and r["cal_s"] == "20"]
    for r in arx:
        if r["all_stable"] != "True":
            continue                         # unstable in open loop (P1-2)
        trans.append(dict(model=f"T2 ARX{r['order']} {r['state']}", size_bytes=float(r["size_bytes_max"]),
                          error_K=float(r["max_K_worst"]), mae_K=float(r["mae_K_mean"]),
                          time_us=float("nan")))
    t4 = EXP / "P3-4_state_space_T4" / "results" / "summary.csv"
    if t4.exists():
        for r in read(t4):
            trans.append(dict(model=r["model"], size_bytes=float(r["size_bytes"]),
                              error_K=float(r["max_K_worst"]), mae_K=float(r["mae_K_mean"]),
                              time_us=float(r["time_us_per_step"])))
    steady = []
    s2 = json.loads((EXP / "P2-1_steady_predictor" / "results" / "summary.json").read_text())["s2_ta"]
    for r in s2:
        if r["variant"] == "S2" and r["k_or_rank"] >= 6:
            continue                         # k >= 6 is the full G again (N = 8)
        name = f"S2 k={r['k_or_rank']}" if r["variant"] == "S2" else f"S2-lr r={r['k_or_rank']}"
        steady.append(dict(model=name, size_bytes=float(r["size_bytes"]),
                           error_K=float(r["max_K_worst"]), mae_K=float(r["mae_K_mean"]),
                           time_us=float("nan")))
    for r in read(EXP / "P2-1_steady_predictor" / "results" / "summary.csv"):
        if r["model"] in ("S0 power blurring", "S1 influence matrix", "S1 float32"):
            steady.append(dict(model=r["model"], size_bytes=float(r["size_bytes_median"]),
                               error_K=float(r["max_K_worst"]), mae_K=float(r["mae_K_mean"]),
                               time_us=float(r["time_us_median"])))
    # prediction times of the models P1-2 / P2-1 did not time (time_untimed.py), if measured
    extra = OUT / "extra_times.csv"
    if extra.exists():
        times = {r["model"]: float(r["time_us"]) for r in read(extra)}
        for g in trans + steady:
            if np.isnan(g["time_us"]) and g["model"] in times:
                g["time_us"] = times[g["model"]]
    for group in (trans, steady):
        idx = pareto([(g["size_bytes"], g["error_K"]) for g in group])
        for i, g in enumerate(group):
            g["pareto"] = i in idx
    save_csv(OUT / "transient_points.csv", trans)
    save_csv(OUT / "steady_points.csv", steady)
    print(md_table(trans, "{:.3g}")); print(); print(md_table(steady, "{:.3g}"))
    save_json(OUT / "summary.json", dict(transient=trans, steady=steady))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, group, title in ((axes[0], trans, "transient (10 s traces, main subset, worst case)"),
                             (axes[1], steady, "steady (24 floorplans, worst case)")):
        draw(fig, ax, group, title)
    fig.savefig(OUT / "pareto.png")

    # one figure per panel, for the Stage 3 report; the transient one without T4 (not reported)
    no_t4 = [dict(g) for g in trans if not g["model"].startswith("T4")]
    idx = pareto([(g["size_bytes"], g["error_K"]) for g in no_t4])
    for i, g in enumerate(no_t4):
        g["pareto"] = i in idx
    for group, title, name in ((no_t4, "transient (10 s traces, main subset, worst case)",
                                "pareto_transient.png"),
                               (steady, "steady (24 floorplans, worst case)", "pareto_steady.png")):
        fig, ax = plt.subplots(figsize=(7.5, 4.6))
        draw(fig, ax, group, title, fontsize=7)
        fig.savefig(OUT / name)


def draw(fig, ax, group, title, fontsize=6):
    """Error against size for one group of models, coloured by prediction time."""
    t = np.array([g["time_us"] for g in group])
    has_t = ~np.isnan(t)
    sc = ax.scatter(np.array([g["size_bytes"] for g in group])[has_t],
                    np.maximum([g["error_K"] for g in group], 1e-7)[has_t],
                    c=t[has_t], cmap="viridis", s=40, zorder=3)
    if (~has_t).any():
        ax.scatter(np.array([g["size_bytes"] for g in group])[~has_t],
                   np.maximum([g["error_K"] for g in group], 1e-7)[~has_t],
                   facecolors="none", edgecolors="grey", s=40, zorder=3, label="time not measured")
    for g in group:
        ax.annotate(g["model"], (g["size_bytes"], max(g["error_K"], 1e-7)), fontsize=fontsize,
                    xytext=(3, 3), textcoords="offset points",
                    weight="bold" if g["pareto"] else "normal")
    pts = sorted([(g["size_bytes"], max(g["error_K"], 1e-7)) for g in group if g["pareto"]])
    ax.plot(*zip(*pts), "r--", lw=0.8, label="Pareto front")
    ax.set(xscale="log", yscale="log", xlabel="model size (bytes of coefficients)",
           ylabel="worst max abs error over cores (K)", title=title)
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo, hi * 1.6)                # room for the labels of the largest models
    fig.colorbar(sc, ax=ax, label="prediction time (µs per step / call)")
    ax.legend(fontsize=7)


if __name__ == "__main__":
    main()
