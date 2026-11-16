"""P3-3 add-on: prediction time of the models that P1-2 and P2-1 did not time, so every point in
the Pareto plots has a time.

- ARX (P1-2): every stable (state, order) fitted on the first 20 s of the excitation trace,
  timed per step over a 10 s test trace, median over the main subset.
- S2 / S2-lr (P2-1): every k and rank, timed per call on the steady test vectors, median over the
  24 floorplans.

Uses the cached HotSpot results of P1-1 (calibration runs), P1-2 (traces) and P2-1 (steady test
vectors); any of these that is not cached yet is re-run first (the steady test vectors take a few
minutes). Run with experiments/run.sh-style single-threaded BLAS:

    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$PWD/experiments" python3 experiments/P3-3_pareto/time_untimed.py
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import save_csv, md_table  # noqa: E402
from src.sim import floorplans as F, hotspot as H, datasets  # noqa: E402
from src.ltp import calibrate as C, bench  # noqa: E402
from src.ltp.models import ARX, CompressedG, LowRankG  # noqa: E402

OUT = HERE / "results"
DT = 1e-3
ORDERS = [(1, 1), (2, 2), (3, 3)]


def centres(fp, idx=None):
    """Block centres, as in P2-1."""
    bl = fp.blocks if idx is None else [fp.blocks[i] for i in idx]
    return np.array([[b.x + b.w / 2, b.y + b.h / 2] for b in bl])


def arx_times():
    fps = [F.get(n) for n in F.MAIN_SUBSET]
    specs = [(fp, "excitation", 60_000, "cal") for fp in fps] + \
            [(fp, "phase", 10_000, "test0") for fp in fps]
    res = datasets.traces_many(specs, dt=DT)          # cached (P1-2)
    cals = C.run_calibration_runs_many(fps)          # cached (P1-1)
    out = {}
    for fp, cal, test in zip(fps, res[:len(fps)], res[len(fps):]):
        G = cals[fp.name]["G"]
        for state, idx in (("all blocks", list(range(len(fp.names)))),
                           ("cores only", fp.power_idx)):
            for na, nb in ORDERS:
                m = ARX.calibrate(G[idx], cal["P"][:20_000], cal["T"][:20_000, idx], H.AMBIENT,
                                  na=na, nb=nb)
                t = bench.time_per_step(lambda P, dt: m.transient(P), test["P"], DT)
                out.setdefault((state, f"({na},{nb})"), []).append(t * 1e6)
    return [dict(model=f"T2 ARX{o} {s}", time_us=float(np.median(v))) for (s, o), v in out.items()]


def s2_times():
    fps = F.ta_floorplans() + [F.get("het_a")]
    cals = C.run_calibration_runs_many(fps)          # cached
    tests = datasets.steady_test_many(fps, n=300)    # cached (P2-1)
    out = {}
    for fp in fps:
        G = cals[fp.name]["G"]
        args = [(p,) for p in tests[fp.name]["P"][:50]]
        models = {f"S2 k={k}": CompressedG.calibrate(G, centres(fp, fp.power_idx), centres(fp), k,
                                                     H.AMBIENT) for k in range(fp.n_power)}
        models.update({f"S2-lr r={r}": LowRankG.calibrate(G, r, H.AMBIENT)
                       for r in range(1, fp.n_power + 1)})
        for name, m in models.items():
            out.setdefault(name, []).append(bench.time_call(m.steady, args)[0] * 1e6)
    return [dict(model=k, time_us=float(np.median(v))) for k, v in out.items()]


def main():
    rows = arx_times() + s2_times()
    save_csv(OUT / "extra_times.csv", rows)
    print(md_table(rows, "{:.3g}"))


if __name__ == "__main__":
    main()
