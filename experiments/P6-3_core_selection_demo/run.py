"""P6-3 [WISH]: demo - which cores should run the busy tasks?

Four busy tasks must run on 4 of the 8 cores; busy cores run at the top of their range (big 20 W,
little 10 W), idle cores at the bottom (big 10 W, little 5 W). All C(8,4) = 70 choices are scored
by their hottest core, once with the calibrated S1 and once with HotSpot (70 steady runs).
Questions: is the coolest choice the same? How well do the rankings agree? How long does each
take? Done on one floorplan per style. The same with the hottest cell on the chip as the objective, predicted by S1-hot-max (P2-3: the max over every grid cell inside the cores).
"""
import itertools
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, gridmap as GM
from src.sim.parallel import pmap
from src.ltp import calibrate as C

OUT = results_dir(__file__)
AMB = H.AMBIENT


def hs_job(fp, p):
    r = H.steady(fp, p, group="P6-3", grid_map=True, keep=False)
    cells = GM.block_cells(fp, 64, 64)
    g = r["grid"].ravel()
    return dict(T=r["T"], hot=np.array([g[cells[i]].max() for i in fp.power_idx]),
                wall_s=r["wall_s"])


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    rows, figs = [], []
    for name in F.MAIN_SUBSET:
        fp = F.get(name)
        cal = C.run_calibration_runs(fp)
        G, Gc = cal["G"][fp.power_idx], cal["G_cells"]
        cells = GM.block_cells(fp, 64, 64)
        lo, hi = fp.power_bounds()
        choices = list(itertools.combinations(range(fp.n_power), 4))
        P = np.array([np.where(np.isin(np.arange(fp.n_power), c), hi, lo) for c in choices])
        # S1: score all 70 choices at once
        t0 = time.perf_counter()
        for _ in range(1000):
            s1 = (AMB + P @ G.T).max(1)
        t_s1 = (time.perf_counter() - t0) / 1000
        # S1-hot-max (P2-3): max over every grid cell inside the cores
        allc = np.concatenate([cells[i] for i in fp.power_idx])
        s1hot = (AMB + P @ Gc[allc].T).max(1)
        t0 = time.perf_counter()
        hs = pmap(hs_job, [dict(fp=fp, p=p) for p in P])
        t_hs_wall = time.perf_counter() - t0
        hs_core = np.array([h["T"][fp.power_idx].max() for h in hs])
        hs_hot = np.array([h["hot"].max() for h in hs])
        best = lambda s: choices[int(np.argmin(s))]   # noqa: E731
        lab = lambda c: "+".join(f"{fp.power_names[i].split('_')[1]}{fp.power_types[i][0].upper()}"
                                 for i in c)           # noqa: E731
        rows.append(dict(
            floorplan=name, choices=len(choices),
            best_by_S1=lab(best(s1)), best_by_HotSpot=lab(best(hs_core)),
            same_best=best(s1) == best(hs_core),
            spearman_S1_vs_HotSpot=spearman(s1, hs_core),
            max_score_err_K=float(np.abs(s1 - hs_core).max()),
            best_by_S1hot=lab(best(s1hot)), best_by_HotSpot_hotcell=lab(best(hs_hot)),
            same_best_hot=best(s1hot) == best(hs_hot),
            regret_core_K=float(hs_core[int(np.argmin(s1))] - hs_core.min()),
            regret_hot_K=float(hs_hot[int(np.argmin(s1hot))] - hs_hot.min()),
            spearman_S1hot_vs_HotSpot=spearman(s1hot, hs_hot),
            worst_minus_best_K=float(hs_core.max() - hs_core.min()),
            S1_time_all_70_us=t_s1 * 1e6,
            HotSpot_cpu_s=float(sum(h["wall_s"] for h in hs)), HotSpot_wall_s=t_hs_wall))
        figs.append((name, s1, hs_core))
    save_csv(OUT / "results.csv", rows)
    print(md_table(rows, "{:.3g}"))
    save_json(OUT / "summary.json", rows)
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.2))
    for ax, (name, s1, hs) in zip(axes, figs):
        ax.scatter(hs - 273.15, s1 - 273.15, s=10)
        lim = [min(hs.min(), s1.min()) - 273.15 - 0.5, max(hs.max(), s1.max()) - 273.15 + 0.5]
        ax.plot(lim, lim, "k:", lw=0.8)
        ax.set(xlabel="HotSpot: hottest core (°C)", ylabel="S1 (°C)", title=name)
    fig.savefig(OUT / "scores.png")


if __name__ == "__main__":
    main()
