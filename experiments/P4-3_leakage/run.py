"""P4-3 [OPT]: leakage (power that depends on temperature, so HotSpot is no longer linear).

HotSpot's built-in leakage model (steady state only), per block of the power layer, FILL included:
    P_leak = alpha * area * exp(beta * (T - 383.15 K)),  alpha = 1.5e4 W/m², beta = 0.036 /K
Run with the default alpha and with 10x alpha (a separate build, HotSpot-leak10), on the main
subset, 50 random power vectors each. Predictors:
  S1 (no leakage)        T = T_amb + G P                        (what P1-1 calibrated)
  S1 + leakage loop      T = T_amb + G_all (P + P_leak(T)), iterated to a fixed point, with
                         G_all = influence of *every* block (FILL too: it leaks); same formula
                         as HotSpot, i.e. the leakage model is assumed known.
"""
from pathlib import Path

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, powergen
from src.sim.parallel import pmap
from src.ltp import calibrate as C, bench

OUT = results_dir(__file__)
AMB = H.AMBIENT
BUILDS = {"default (alpha 1.5e4)": (H.HOTSPOT, 1.5e4),
          "10x (alpha 1.5e5)": (Path.home() / "projects" / "HotSpot-leak10" / "hotspot", 1.5e5)}
BETA, TBASE = 0.036, 383.15


def run(fp, p, binary, leak):
    H.HOTSPOT = binary
    return H.steady(fp, p, group="P4-3", extra={"leakage_used": 1} if leak else None,
                    keep=False)["T"]


def unit_all(fp, b):
    p = np.zeros(len(fp.blocks)); p[b] = 1.0
    return H.steady(fp, p, group="P4-3", keep=False)["T"] - AMB


def leak_power(fp, T, alpha):
    area = np.array([b.area for b in fp.blocks])
    return alpha * area * np.exp(BETA * (T - TBASE))


def fixed_point(G_all, fp, Pfull, alpha, tol=1e-4, iters=100):
    T = AMB + G_all @ Pfull
    for k in range(iters):
        Tn = AMB + G_all @ (Pfull + leak_power(fp, T, alpha))
        if np.abs(Tn - T).max() < tol:
            return Tn, k + 1
        T = Tn
    return T, iters


def main():
    fps = [F.get(n) for n in F.MAIN_SUBSET]
    cals = C.run_calibration_runs_many(fps)
    rows = []
    for fp in fps:
        core = fp.power_idx
        G_all = np.column_stack(pmap(unit_all, [dict(fp=fp, b=b) for b in range(len(fp.blocks))]))
        G = cals[fp.name]["G"]
        Ps = powergen.random_steady(fp, 50, seed=8)
        for label, (binary, alpha) in BUILDS.items():
            T = np.array(pmap(run, [dict(fp=fp, p=p, binary=binary, leak=True) for p in Ps]))
            pred0 = AMB + Ps @ G.T
            fpres = [fixed_point(G_all, fp, fp.full_power(p), alpha) for p in Ps]
            pred1 = np.array([r[0] for r in fpres])
            leak_W = np.array([leak_power(fp, t, alpha).sum() for t in T])
            t_us = bench.time_call(lambda p: fixed_point(G_all, fp, fp.full_power(p), alpha),
                                   [(p,) for p in Ps[:20]], repeats=2000, warmup=50)[0] * 1e6
            for name, pr, extra in (("S1 (no leakage)", pred0, {}),
                                    ("S1 + leakage loop", pred1,
                                     dict(iterations_mean=float(np.mean([r[1] for r in fpres])),
                                          time_us=t_us))):
                err = pr[:, core] - T[:, core]
                rows.append(dict(floorplan=fp.name, leakage=label, model=name,
                                 mae_K=float(np.abs(err).mean()), max_K=float(np.abs(err).max()),
                                 leak_W_mean=float(leak_W.mean()),
                                 leak_rise_K_mean=float((T[:, core] - pred0[:, core]).mean()),
                                 **extra))
        print(fp.name, "done")
    keys = ["floorplan", "leakage", "model", "mae_K", "max_K", "leak_W_mean", "leak_rise_K_mean",
            "iterations_mean", "time_us"]
    rows = [{k: r.get(k, "") for k in keys} for r in rows]
    save_csv(OUT / "results.csv", rows)
    print(md_table(rows, "{:.3g}"))
    save_json(OUT / "summary.json", rows)


if __name__ == "__main__":
    main()
