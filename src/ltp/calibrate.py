"""calibrate.py: the one-time, per-floorplan calibration stage (docs/plan.md P1-1).

For each power block j of the floorplan:
  - one steady HotSpot run with 1 W in block j alone   -> column j of G (and of the 64x64 map)
  - one transient run, 1 W step in block j, from cold:
        fine   dt = 1 ms,  2,000 steps (0-2 s)       fast silicon / TIM dynamics
        coarse dt = 20 ms, 5,000 steps (0-100 s)     slow spreader / heat-sink tail
HotSpot is linear (P0-2), so these 3N runs determine every model: S1 from the steady runs,
T1 and T3 from the step responses. Raw results are cached in $LTP_RUNS/calib/<floorplan>.npz.
"""
import time

import numpy as np

from src.sim import hotspot as H
from src.sim.parallel import pmap

FINE = (1e-3, 2000)
COARSE = (0.02, 5000)
T_SWITCH = 2.0          # use fine samples up to here, coarse samples after
CACHE = H.RUNS / "calib"


def _unit(fp, j):
    p = np.zeros(fp.n_power)
    p[j] = 1.0
    return p


def _steady_job(fp, j, extra=None):
    return H.steady(fp, _unit(fp, j), group=f"calib/{fp.name}", grid_map=True, keep=False,
                    extra=extra)


def _step_job(fp, j, dt, steps, extra=None):
    P = np.tile(_unit(fp, j), (steps, 1))
    return H.transient(fp, P, dt, group=f"calib/{fp.name}", keep=False, extra=extra)


def run_calibration_runs(fp, refresh=False, variant=None):
    """All 3N HotSpot runs for one floorplan (cached). Returns a dict of arrays."""
    return run_calibration_runs_many([fp], refresh, variant)[fp.name]


def run_calibration_runs_many(fps, refresh=False, variant=None):
    """Calibration runs for several floorplans in one worker pool (longest jobs first).

    variant: None for the base package, or dict(tag=..., extra={hotspot option: value},
    ambient=K) for a changed package (P4-2); cached separately under the tag.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    extra = None if variant is None else variant["extra"]
    suffix = "" if variant is None else f"_{variant['tag']}"
    path = lambda fp: CACHE / f"{fp.name}{suffix}.npz"   # noqa: E731
    out = {fp.name: dict(np.load(path(fp))) for fp in fps if path(fp).exists() and not refresh}
    todo = [fp for fp in fps if fp.name not in out]
    if not todo:
        return out
    jobs = []
    for fp in todo:
        for j in range(fp.n_power):
            jobs += [("coarse", fp, j, (_step_job, dict(fp=fp, j=j, dt=COARSE[0], steps=COARSE[1],
                                                          extra=extra))),
                     ("fine", fp, j, (_step_job, dict(fp=fp, j=j, dt=FINE[0], steps=FINE[1],
                                                      extra=extra))),
                     ("steady", fp, j, (_steady_job, dict(fp=fp, j=j, extra=extra)))]
    order = {"coarse": 0, "fine": 1, "steady": 2}
    jobs.sort(key=lambda x: order[x[0]])
    t0 = time.perf_counter()
    res = pmap(_dispatch, [dict(job=j[3]) for j in jobs])
    pool_wall = time.perf_counter() - t0
    amb = H.AMBIENT if variant is None else variant["ambient"]
    for fp in todo:
        N = fp.n_power
        get = {kind: [None] * N for kind in order}
        for (kind, f, j, _), r in zip(jobs, res):
            if f.name == fp.name:
                get[kind][j] = r
        st, fine, coarse = get["steady"], get["fine"], get["coarse"]
        cal = dict(
            G=np.column_stack([r["T"] - amb for r in st]),                     # (n_out, N)
            G_cells=np.stack([r["grid"].ravel() - amb for r in st], axis=1),   # (cells, N)
            Y_fine=np.stack([r["T"] - amb for r in fine], axis=2),             # (K, n_out, N)
            Y_coarse=np.stack([r["T"] - amb for r in coarse], axis=2),
            t_fine=FINE[0] * np.arange(1, FINE[1] + 1),       # row k = end of step k
            t_coarse=COARSE[0] * np.arange(1, COARSE[1] + 1),
            hotspot_s_steady=np.array([r["wall_s"] for r in st]),
            hotspot_s_transient=np.array([r["wall_s"] for r in fine + coarse]),
            pool_wall_s=np.array(pool_wall),
            n_floorplans_in_pool=np.array(len(todo)),
        )
        np.savez(path(fp), **cal)
        out[fp.name] = cal
    return out


def steady_unit_runs(fp, refresh=False):
    """Only the N steady unit runs (enough for S1/S2), cached in $LTP_RUNS/calib/<fp>_steady.npz.
    Used for the large generated floorplans where only the steady model-size story is needed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{fp.name}_steady.npz"
    if path.exists() and not refresh:
        return dict(np.load(path))
    res = pmap(_steady_job, [dict(fp=fp, j=j) for j in range(fp.n_power)])
    cal = dict(G=np.column_stack([r["T"] - H.AMBIENT for r in res]),
               G_cells=np.stack([r["grid"].ravel() - H.AMBIENT for r in res], axis=1),
               hotspot_s_steady=np.array([r["wall_s"] for r in res]))
    np.savez(path, **cal)
    return cal


def _dispatch(job):
    fn, kw = job
    return fn(**kw)


def merged_samples(cal, n=160):
    """Log-spaced sample times from 1 ms to 100 s: fine data up to T_SWITCH, coarse after."""
    targets = np.logspace(np.log10(cal["t_fine"][0]), np.log10(cal["t_coarse"][-1]), n)
    t, Y = [], []
    for tt in targets:
        if tt <= T_SWITCH:
            k = int(np.argmin(np.abs(cal["t_fine"] - tt)))
            t.append(cal["t_fine"][k]); Y.append(cal["Y_fine"][k])
        else:
            k = int(np.argmin(np.abs(cal["t_coarse"] - tt)))
            t.append(cal["t_coarse"][k]); Y.append(cal["Y_coarse"][k])
    t = np.array(t)
    _, keep = np.unique(t, return_index=True)
    return t[keep], np.array(Y)[keep]
