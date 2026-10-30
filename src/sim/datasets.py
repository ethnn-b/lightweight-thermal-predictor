"""datasets.py: HotSpot ground-truth test sets, generated from seeds and cached.

Test inputs are never used for calibration (plan.md §6). Seeds are derived from the floorplan
name, so every experiment that asks for the same set gets exactly the same data.
Cache: $LTP_RUNS/datasets/<name>.npz
"""
import zlib

import numpy as np

from src.sim import hotspot as H, powergen
from src.sim.parallel import pmap

CACHE = H.RUNS / "datasets"


def _seed(fp_name, salt):
    return zlib.crc32(f"{fp_name}/{salt}".encode())


def _steady_job(fp, p):
    return H.steady(fp, p, group=f"datasets/{fp.name}", keep=False)["T"]


def _trace_job(fp, P, dt):
    r = H.transient(fp, P, dt, group=f"datasets/{fp.name}", keep=False)
    return dict(T=r["T"], wall_s=r["wall_s"])


TRACE_KINDS = {"phase": powergen.phase_trace, "excitation": powergen.excitation_trace}


def traces_many(specs, dt=1e-3):
    """HotSpot transients from a cold chip, cached.

    specs: list of (fp, kind, steps, salt[, kwargs]) with kind in TRACE_KINDS, or
    (fp, "custom", P, salt) with an explicit power trace P (cached under the salt name).
    Returns a list of dict(P, T, wall_s) in the same order.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    out, todo = [None] * len(specs), []
    for k, spec in enumerate(specs):
        fp, kind, arg, salt = spec[:4]
        kw = spec[4] if len(spec) > 4 else {}
        if kind == "custom":
            P, tag = np.asarray(arg, float), f"custom_{salt}"
        else:
            P = TRACE_KINDS[kind](fp, arg, seed=_seed(fp.name, f"{kind}/{salt}"), **kw)
            tag = f"{kind}_{arg}_{salt}"
        path = CACHE / f"trace_{fp.name}_{tag}_dt{dt:g}.npz"
        if path.exists():
            out[k] = dict(np.load(path))
        else:
            todo.append((k, fp, P, path))
    todo.sort(key=lambda x: -len(x[2]))                  # longest first
    res = pmap(_trace_job, [dict(fp=fp, P=P, dt=dt) for _, fp, P, _ in todo])
    for (k, fp, P, path), r in zip(todo, res):
        d = dict(P=P, T=r["T"], wall_s=np.array(r["wall_s"]))
        np.savez(path, **d)
        out[k] = d
    return out


def steady_test_many(fps, n=300):
    """Per floorplan: the TA nominal vector, the max vector, then n random vectors (all within
    the TA ranges). Returns {name: dict(P=(n+2, N), T=(n+2, n_blocks))}."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out, todo = {}, []
    for fp in fps:
        path = CACHE / f"steady_{fp.name}_{n}.npz"
        if path.exists():
            out[fp.name] = dict(np.load(path))
        else:
            P = np.vstack([fp.nominal_power(), fp.max_power(),
                           powergen.random_steady(fp, n, _seed(fp.name, "steady_test"))])
            todo.append((fp, P))
    jobs = [dict(fp=fp, p=p) for fp, P in todo for p in P]
    res = pmap(_steady_job, jobs)
    k = 0
    for fp, P in todo:
        T = np.array(res[k:k + len(P)])
        k += len(P)
        np.savez(CACHE / f"steady_{fp.name}_{n}.npz", P=P, T=T)
        out[fp.name] = dict(P=P, T=T)
    return out
