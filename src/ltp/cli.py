"""ltp command line.

    python3 -m src.ltp calibrate <floorplan> -o model.npz [--M 4]
    python3 -m src.ltp steady    model.npz  (--power 20,20,8,... | --ptrace file.ptrace) [-o out.steady]
    python3 -m src.ltp transient model.npz  --ptrace file.ptrace --dt 0.001 [-o out.ttrace]
    python3 -m src.ltp forecast  model.npz  --history h.ptrace --temps T_now.txt
                                            --next next.ptrace --dt 0.001
    python3 -m src.ltp bench     model.npz  <floorplan>

<floorplan> is a TA-style folder (with .lcf and *_layer_0.flp), a TA name such as s4_fp003,
or het_a / hom_16 / ev6. calibrate and bench run HotSpot (inside WSL); everything else needs only
NumPy and the model file. Temperatures are printed in degrees C.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

from .predictor import Predictor


def _floorplan(arg):
    from src.sim import floorplans as F
    p = Path(arg)
    if p.is_dir():
        return F.from_folder(p)
    return F.get(arg)


def _read_ptrace(path, power_names):
    lines = [l for l in Path(path).read_text().splitlines() if l.strip()]
    names = lines[0].split()
    vals = np.array([[float(v) for v in l.split()] for l in lines[1:]])
    idx = [names.index(n) for n in power_names]
    return vals[:, idx]


def _print_T(names, T):
    T = np.atleast_2d(T)
    print("\t".join(names))
    for row in T:
        print("\t".join(f"{v - 273.15:.3f}" for v in row))


def cmd_calibrate(a):
    from src.ltp import calibrate as C
    from src.sim import gridmap as GM
    from src.ltp.models import SumExp
    from src.sim import hotspot as H
    fp = _floorplan(a.floorplan)
    t0 = time.perf_counter()
    cal = C.run_calibration_runs(fp, refresh=a.refresh)
    t, Y = C.merged_samples(cal)
    t3 = SumExp.calibrate(cal["G"], t, Y, a.M, H.AMBIENT)
    cells = GM.block_cells(fp, 64, 64)
    m = cal["G_cells"] @ fp.nominal_power()
    hot = [cells[i][np.argmax(m[cells[i]])] for i in fp.power_idx]
    pred = Predictor(fp.names, fp.power_names, H.AMBIENT, cal["G"], t3.A, t3.tau,
                     G_hot=cal["G_cells"][hot], hot_names=fp.power_names)
    pred.save(a.output, floorplan=fp.name)
    print(f"calibrated {fp.name}: {3 * fp.n_power} HotSpot runs, "
          f"{time.perf_counter() - t0:.1f} s; model {pred.size_bytes()} B of coefficients "
          f"-> {a.output}")


def _write_T(path, names, T):
    """HotSpot .ttrace-style file: header of block names, one row per step, kelvin, 6 decimals."""
    with open(path, "w") as f:
        f.write("\t".join(names) + "\n")
        for row in np.atleast_2d(T):
            f.write("\t".join(f"{v:.6f}" for v in row) + "\n")


def cmd_steady(a):
    p = Predictor.load(a.model)
    P = (np.array([[float(x) for x in a.power.split(",")]]) if a.power
         else _read_ptrace(a.ptrace, p.power_names))
    T = p.steady(P)
    _print_T(p.names, T)
    if a.output:
        _write_T(a.output, p.names, T)


def cmd_transient(a):
    p = Predictor.load(a.model)
    P = _read_ptrace(a.ptrace, p.power_names)
    z0 = p.initial_state(P[0]) if a.warm else None
    T = p.transient(P, a.dt, z0=z0)
    if a.output:
        _write_T(a.output, p.names, T)
    else:
        _print_T(p.names, T)


def cmd_forecast(a):
    p = Predictor.load(a.model)
    hist = _read_ptrace(a.history, p.power_names)
    nxt = _read_ptrace(a.next, p.power_names)
    T_now = np.array([float(x) + 273.15 for x in Path(a.temps).read_text().split()])
    z = p.run_state(hist, a.dt)
    _print_T(p.names, p.forecast(T_now, z, nxt, a.dt))


def cmd_bench(a):
    from src.sim import datasets
    from src.ltp import bench
    p = Predictor.load(a.model)
    fp = _floorplan(a.floorplan)
    core = fp.power_idx
    st = datasets.steady_test_many([fp], n=a.n)[fp.name]
    err = p.steady(st["P"])[:, core] - st["T"][:, core]
    t_s = bench.time_call(p.steady, [(x,) for x in st["P"][:50]])[0]
    tr = datasets.traces_many([(fp, "phase", a.steps, "bench")])[0]
    Tm = p.transient(tr["P"], 1e-3)
    e2 = Tm[:, core] - tr["T"][:, core]
    t_t = bench.time_per_step(p.transient, tr["P"], 1e-3)
    print(f"model {a.model}: {p.size_bytes()} B of coefficients "
          f"(G {8 * p.G.size} B, T3 {8 * (p.A.size + p.tau.size)} B, M = {len(p.tau)})")
    print(f"steady    vs HotSpot on {len(st['P'])} vectors: MAE {np.abs(err).mean():.2e} K, "
          f"max {np.abs(err).max():.2e} K, {t_s * 1e6:.1f} us per call")
    print(f"transient vs HotSpot on {a.steps} steps (1 ms): MAE {np.abs(e2).mean():.3f} K, "
          f"max {np.abs(e2).max():.3f} K, {t_t * 1e6:.1f} us per step")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ltp", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate"); c.add_argument("floorplan"); c.add_argument("-o", "--output", required=True)
    c.add_argument("--M", type=int, default=4); c.add_argument("--refresh", action="store_true")
    s = sub.add_parser("steady"); s.add_argument("model")
    g = s.add_mutually_exclusive_group(required=True); g.add_argument("--power"); g.add_argument("--ptrace")
    s.add_argument("-o", "--output", help="also write the temperatures (K, 6 decimals) to this file")
    t = sub.add_parser("transient"); t.add_argument("model"); t.add_argument("--ptrace", required=True)
    t.add_argument("--dt", type=float, default=1e-3); t.add_argument("-o", "--output")
    t.add_argument("--warm", action="store_true", help="start at the steady state of the first row")
    f = sub.add_parser("forecast"); f.add_argument("model")
    for k in ("--history", "--temps", "--next"):
        f.add_argument(k, required=True)
    f.add_argument("--dt", type=float, default=1e-3)
    b = sub.add_parser("bench"); b.add_argument("model"); b.add_argument("floorplan")
    b.add_argument("--n", type=int, default=300); b.add_argument("--steps", type=int, default=2000)
    a = ap.parse_args(argv)
    {"calibrate": cmd_calibrate, "steady": cmd_steady, "transient": cmd_transient,
     "forecast": cmd_forecast, "bench": cmd_bench}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
