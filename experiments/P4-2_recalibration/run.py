"""P4-2 [OPT]: recalibration after a package change.

Two floorplans (s1_fp001, s4_fp001), three package changes (as IC-ThermBench varies them):
  ambient 35 C instead of 45 C            -> expect: no recalibration, only T_amb moves
  heat-sink convection resistance x2     (r_convec 0.1 -> 0.2 K/W, a worse cooler)
  heat-sink convection resistance x0.5   (r_convec 0.1 -> 0.05 K/W, a better cooler)
For each: the old (base) S1/T3 models vs HotSpot under the new package, then the recalibrated
models (the same 3N runs as P1-1) and their cost.
Tests: 50 random steady vectors, and a 3 s phase trace (dt = 1 ms) from a cold chip.
"""
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, powergen
from src.sim.parallel import pmap
from src.ltp import calibrate as C
from src.ltp.models import SumExp

OUT = results_dir(__file__)
FPS = ["s1_fp001", "s4_fp001"]
VARIANTS = [
    dict(tag="amb35", label="ambient 35 °C", extra={"ambient": 308.15, "init_temp": 308.15},
         ambient=308.15),
    dict(tag="rconv0.2", label="r_convec ×2 (0.2 K/W)", extra={"r_convec": 0.2}, ambient=H.AMBIENT),
    dict(tag="rconv0.05", label="r_convec ×0.5 (0.05 K/W)", extra={"r_convec": 0.05},
         ambient=H.AMBIENT),
]
DT, STEPS = 1e-3, 3000


def steady_job(fp, p, extra):
    return H.steady(fp, p, group="P4-2", extra=extra, keep=False)["T"]


def trans_job(fp, P, extra):
    return H.transient(fp, P, DT, group="P4-2", extra=extra, keep=False)["T"]


def fit(cal, amb):
    t, Y = C.merged_samples(cal)
    return cal["G"], SumExp.calibrate(cal["G"], t, Y, 4, amb)


def main():
    fps = [F.get(n) for n in FPS]
    base = C.run_calibration_runs_many(fps)
    rows = []
    for v in VARIANTS:
        t0 = time.perf_counter()
        new = C.run_calibration_runs_many(fps, variant=v)
        recal_wall = time.perf_counter() - t0
        for fp in fps:
            core = fp.power_idx
            Ps = powergen.random_steady(fp, 50, seed=5)
            Pt = powergen.phase_trace(fp, STEPS, seed=6, max_phase=1000)
            res = pmap(steady_job, [dict(fp=fp, p=p, extra=v["extra"]) for p in Ps])
            Ts = np.array(res)
            Tt = trans_job(fp, Pt, v["extra"])
            G0, t30 = fit(base[fp.name], H.AMBIENT)
            G1, t31 = fit(new[fp.name], v["ambient"])
            preds = {
                "old model, old ambient": (H.AMBIENT + Ps @ G0.T,
                                           SumExp(t30.A, t30.tau, H.AMBIENT).transient(Pt, DT)),
                "old model, new T_amb only": (v["ambient"] + Ps @ G0.T,
                                              SumExp(t30.A, t30.tau, v["ambient"]).transient(Pt, DT)),
                "recalibrated": (v["ambient"] + Ps @ G1.T, t31.transient(Pt, DT)),
            }
            for name, (ps, pt) in preds.items():
                if v["tag"] != "amb35" and name == "old model, old ambient":
                    continue
                rows.append(dict(variant=v["label"], floorplan=fp.name, model=name,
                                 steady_max_K=float(np.abs(ps[:, core] - Ts[:, core]).max()),
                                 transient_max_K=float(np.abs(pt[:, core] - Tt[:, core]).max()),
                                 transient_mae_K=float(np.abs(pt[:, core] - Tt[:, core]).mean())))
            rows.append(dict(variant=v["label"], floorplan=fp.name, model="(recalibration cost)",
                             steady_max_K=float("nan"), transient_max_K=float("nan"),
                             transient_mae_K=float("nan"),
                             hotspot_runs=3 * fp.n_power,
                             hotspot_cpu_s=float(new[fp.name]["hotspot_s_steady"].sum()
                                                 + new[fp.name]["hotspot_s_transient"].sum()),
                             pool_wall_s=recal_wall / len(fps)))
            print(v["tag"], fp.name, "done")
    keys = ["variant", "floorplan", "model", "steady_max_K", "transient_max_K", "transient_mae_K",
            "hotspot_runs", "hotspot_cpu_s", "pool_wall_s"]
    rows = [{k: r.get(k, "") for k in keys} for r in rows]
    save_csv(OUT / "results.csv", rows)
    print(md_table([r for r in rows if r["model"] != "(recalibration cost)"], "{:.3g}"))
    print(md_table([r for r in rows if r["model"] == "(recalibration cost)"], "{:.3g}"))
    save_json(OUT / "summary.json", rows)


if __name__ == "__main__":
    main()
