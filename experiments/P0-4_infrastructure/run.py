"""P0-4: check and time the HotSpot infrastructure.

  1. The LU-caching patch gives bit-identical transient output to precision-only HotSpot, and
     how much faster it is.
  2. HotSpot cost: one steady run on every TA floorplan; transient cost per step (fit
     wall = setup + per_step * steps) for the grid 64x64 reference.
  3. Throughput of parallel runs (src/sim/parallel.py).
These are the HotSpot numbers that the predictor's prediction time is compared against.
"""
import os
import time
from pathlib import Path

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, powergen
from src.sim.parallel import pmap, WORKERS

OUT = results_dir(__file__)
G = "P0-4"
PREC = Path.home() / "projects" / "HotSpot-prec" / "hotspot"


def steady_job(fp_name):
    fp = F.get(fp_name)
    return H.steady(fp, fp.nominal_power(), group=G, keep=False)["wall_s"]


def main():
    fp = F.get("s4_fp001")
    P = powergen.phase_trace(fp, 300, seed=3, max_phase=100)

    # 1. patched vs precision-only build
    fast = H.transient(fp, P, 1e-3, group=G)
    H.HOTSPOT, saved = PREC, H.HOTSPOT
    slow = H.transient(fp, P, 1e-3, group=G)
    H.HOTSPOT = saved
    same = (Path(fast["dir"]) / "out.ttrace").read_bytes() == (Path(slow["dir"]) / "out.ttrace").read_bytes()
    patch = dict(steps=len(P), identical_output=bool(same),
                 max_abs_diff_K=float(np.abs(fast["T"] - slow["T"]).max()),
                 precision_only_s=slow["wall_s"], ltp_build_s=fast["wall_s"],
                 speedup=slow["wall_s"] / fast["wall_s"])
    print(md_table([patch], "{:.4g}"))

    # 2a. steady run on every TA floorplan (sequential, nothing else running)
    st = [dict(floorplan=f.name, style=f.style, steady_wall_s=steady_job(f.name))
          for f in F.ta_floorplans()]
    save_csv(OUT / "steady_timing.csv", st)

    # 2b. transient cost vs number of steps, on the main subset
    tr = []
    for name in F.MAIN_SUBSET:
        f = F.get(name)
        for steps in (100, 1000, 5000):
            Pk = powergen.phase_trace(f, steps, seed=4, max_phase=500)
            tr.append(dict(floorplan=name, steps=steps,
                           wall_s=H.transient(f, Pk, 1e-3, group=G, keep=False)["wall_s"]))
    save_csv(OUT / "transient_timing.csv", tr)
    fits = []
    for name in F.MAIN_SUBSET:
        s = np.array([r["steps"] for r in tr if r["floorplan"] == name], float)
        w = np.array([r["wall_s"] for r in tr if r["floorplan"] == name])
        per_step, setup = np.polyfit(s, w, 1)
        fits.append(dict(floorplan=name, setup_s=setup, per_step_ms=per_step * 1e3))
    print(md_table(fits, "{:.3g}"))

    # 3. parallel throughput: 92 steady runs at several worker counts
    names = [f.name for f in F.ta_floorplans()] * 4
    par = []
    for w in (1, 2, 4, 8, 12, 16):
        t0 = time.perf_counter()
        walls = pmap(steady_job, [dict(fp_name=n) for n in names], workers=w)
        dt = time.perf_counter() - t0
        par.append(dict(workers=w, runs=len(names), wall_s=dt, runs_per_s=len(names) / dt,
                        median_run_s=float(np.median(walls))))
    save_csv(OUT / "parallel_scaling.csv", par)
    print(md_table(par, "{:.3g}"))

    walls = np.array([r["steady_wall_s"] for r in st])
    summary = dict(patch=patch, steady_median_s=float(np.median(walls)),
                   steady_min_s=float(walls.min()), steady_max_s=float(walls.max()),
                   transient_fit=fits, parallel=par, cpus=os.cpu_count(), default_workers=WORKERS)
    save_json(OUT / "summary.json", summary)
    print(f"steady: median {np.median(walls):.3f} s, range {walls.min():.3f}-{walls.max():.3f} s")

    fig, ax = plt.subplots(figsize=(4.5, 3))
    for name in F.MAIN_SUBSET:
        rr = [r for r in tr if r["floorplan"] == name]
        ax.plot([r["steps"] for r in rr], [r["wall_s"] for r in rr], "o-", label=name)
    ax.set(xlabel="transient steps (Δt = 1 ms)", ylabel="HotSpot wall time (s)",
           title="grid 64×64 transient cost")
    ax.legend()
    fig.savefig(OUT / "transient_timing.png")


if __name__ == "__main__":
    main()
