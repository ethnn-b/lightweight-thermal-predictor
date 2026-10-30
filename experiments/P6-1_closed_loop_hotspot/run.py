"""P6-1 [WISH]: closed-loop HotSpot for DTM.

DTM needs a 'chip' whose power can change every interval in response to its temperature.
src/sim/stepper.py runs HotSpot's transient with the power trace on a pipe and the temperature
trace on a FIFO, one row at a time (the patched build flushes every row). Checks:
  1. the stepper gives exactly the same temperatures as an ordinary HotSpot run on the same trace
     (cold start, and warm start from a .steady file);
  2. its cost per step (Python <-> HotSpot round trip included).
"""
import time

import numpy as np

from common import results_dir, save_json, md_table
from src.sim import floorplans as F, hotspot as H, powergen
from src.sim.stepper import HotSpotStepper

OUT = results_dir(__file__)
DT, STEPS = 1e-3, 1000


def main():
    rows = []
    for name in ["s1_fp001", "s4_fp001"]:
        fp = F.get(name)
        P = powergen.phase_trace(fp, STEPS, seed=21, max_phase=300)
        st = H.steady(fp, P.mean(0), group="P6-1")
        init = f"{st['dir']}/out.steady"
        for start, kw in (("cold", {}), ("warm", dict(init=init))):
            ref = H.transient(fp, P, DT, group="P6-1", **kw)
            t0 = time.perf_counter()
            with HotSpotStepper(fp, DT, **kw) as chip:
                T = np.array([chip.step(p) for p in P])
            wall = time.perf_counter() - t0
            rows.append(dict(floorplan=name, start=start, steps=STEPS,
                             max_diff_vs_batch_K=float(np.abs(T - ref["T"]).max()),
                             stepper_ms_per_step=wall / STEPS * 1e3,
                             batch_ms_per_step=ref["wall_s"] / STEPS * 1e3))
    print(md_table(rows, "{:.3g}"))
    save_json(OUT / "summary.json", rows)


if __name__ == "__main__":
    main()
