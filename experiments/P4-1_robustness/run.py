"""P4-1: where does the calibrated predictor break? (no new models, only new test inputs)

Main subset; S1 (steady) and T3 M = 4 / T2 ARX (2,2) all-blocks (transient), calibrated as before.
  (a) power above the calibration range: steady vectors at 1.5x and 3x the TA maximum;
      a transient trace at 2x
  (b) bursty: every core switches level every 1-5 ms (3 s)
  (c) task migration: one heavy task (top of range) hops between cores every 300 ms, big <-> little,
      the rest idle at the bottom of their range (3 s)
  (d) another step size: HotSpot and the models at Δt = 0.1 ms (0.3 s) and 10 ms (10 s)
  (e) warm start: HotSpot starts from the steady state of the first power row (-init_file);
      the models start from their own steady state for that row (3 s)
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table
from src.sim import floorplans as F, hotspot as H, powergen, datasets
from src.sim.parallel import pmap
from src.ltp import calibrate as C
from src.ltp.models import SumExp, ARX

OUT = results_dir(__file__)
AMB = H.AMBIENT


def steady_job(fp, p):
    return H.steady(fp, p, group="P4-1", keep=False)["T"]


def trans_job(fp, P, dt, warm, tag):
    cache = H.RUNS / "P4-1" / f"{fp.name}_{tag}.npz"
    if cache.exists():
        return np.load(cache)["T"]
    init = None
    if warm:
        st = H.steady(fp, P[0], group="P4-1")
        init = f"{st['dir']}/out.steady"
    T = H.transient(fp, P, dt, group="P4-1", init=init, keep=False)["T"]
    np.savez(cache, T=T, P=P)
    return T


def migration_trace(fp, steps, hop, seed):
    rng = np.random.default_rng(seed)
    lo, hi = fp.power_bounds()
    P = np.tile(lo, (steps, 1))
    order = rng.permutation(fp.n_power)
    for k in range(0, steps, hop):
        j = order[(k // hop) % fp.n_power]
        P[k:k + hop, j] = hi[j]
    return P


def main():
    fps = [F.get(n) for n in F.MAIN_SUBSET]
    cals = C.run_calibration_runs_many(fps)
    cal_tr = datasets.traces_many([(fp, "excitation", 60000, "cal") for fp in fps])
    jobs, meta = [], []
    for fp in fps:
        lo, hi = fp.power_bounds()
        for scale in (1.5, 3.0):
            for p in hi * scale * np.random.default_rng(42).uniform(0.6, 1.0, (30, fp.n_power)):
                jobs.append((steady_job, dict(fp=fp, p=p)))
                meta.append((fp.name, f"(a) steady at {scale}x max", None, None))
        cases = {
            "(a) transient at 2x": (2 * powergen.phase_trace(fp, 3000, seed=43, max_phase=500), 1e-3, False),
            "(b) bursty 1-5 ms": (powergen.phase_trace(fp, 3000, seed=44, min_phase=1, max_phase=5), 1e-3, False),
            "(c) task migration": (migration_trace(fp, 3000, 300, seed=45), 1e-3, False),
            "(d) dt = 0.1 ms": (powergen.phase_trace(fp, 3000, seed=46, max_phase=300), 1e-4, False),
            "(d) dt = 10 ms": (powergen.phase_trace(fp, 1000, seed=47, max_phase=100), 1e-2, False),
            "(e) warm start": (powergen.phase_trace(fp, 3000, seed=48, max_phase=500), 1e-3, True),
            "(ref) normal phase trace": (powergen.phase_trace(fp, 3000, seed=49, max_phase=500), 1e-3, False),
        }
        for name, (P, dt, warm) in cases.items():
            tag = "".join(c for c in name if c.isalnum())
            jobs.append((trans_job, dict(fp=fp, P=P, dt=dt, warm=warm, tag=tag)))
            meta.append((fp.name, name, P, (dt, warm)))
    res = pmap(_dispatch, [dict(job=j) for j in jobs])

    rows = []
    models = {}
    for fp, ct in zip(fps, cal_tr):
        cal = cals[fp.name]
        t, Y = C.merged_samples(cal)
        allb = list(range(len(fp.names)))
        models[fp.name] = dict(
            G=cal["G"], t3=SumExp.calibrate(cal["G"], t, Y, 4, AMB),
            arx=ARX.calibrate(cal["G"], ct["P"][:20000], ct["T"][:20000], AMB, 2, 2))
    steady_acc = {}
    for (name, case, P, extra), T in zip(meta, res):
        fp = F.get(name)
        core = fp.power_idx
        m = models[name]
        if extra is None:
            steady_acc.setdefault((name, case), []).append((T, None))
            continue
        dt, warm = extra
        z0 = m["t3"].steady_state_z(P[0]) if warm else None
        preds = {"T3 M=4": m["t3"].transient(P, dt, z0=z0)}
        if dt == 1e-3:
            xh = ph = None
            if warm:                      # history: steady state of the first row, at that power
                x0 = m["G"] @ P[0]
                xh, ph = [x0, x0], [P[0], P[0]]
            preds["T2 ARX(2,2)"] = m["arx"].transient(P, x_hist=xh, p_hist=ph)
        for mn, pr in preds.items():
            e = pr[:, core] - T[:, core]
            rows.append(dict(floorplan=name, case=case, model=mn, mae_K=float(np.abs(e).mean()),
                             max_K=float(np.abs(e).max()),
                             max_K_after_50_steps=float(np.abs(e[50:]).max()),
                             max_rise_K=float((T[:, core] - AMB).max())))
    # steady cases: rebuild the inputs in the same order
    k = 0
    for fp in fps:
        hi = fp.power_bounds()[1]
        for scale in (1.5, 3.0):
            Ps = hi * scale * np.random.default_rng(42).uniform(0.6, 1.0, (30, fp.n_power))
            Ts = np.array([x[0] for x in steady_acc[(fp.name, f"(a) steady at {scale}x max")]])
            e = (AMB + Ps @ models[fp.name]["G"].T - Ts)[:, fp.power_idx]
            rows.append(dict(floorplan=fp.name, case=f"(a) steady at {scale}x max", model="S1",
                             mae_K=float(np.abs(e).mean()), max_K=float(np.abs(e).max()),
                             max_rise_K=float((Ts[:, fp.power_idx] - AMB).max())))
    save_csv(OUT / "all_results.csv", rows)
    cases = sorted(set(r["case"] for r in rows))
    summ = []
    for c in cases:
        for mn in ("S1", "T3 M=4", "T2 ARX(2,2)"):
            rr = [r for r in rows if r["case"] == c and r["model"] == mn]
            if rr:
                summ.append(dict(case=c, model=mn, mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                                 max_K_worst=float(np.max([r["max_K"] for r in rr])),
                                 max_K_after_50=float(np.max([r.get("max_K_after_50_steps", np.nan)
                                                              for r in rr])),
                                 max_rise_K=float(np.max([r["max_rise_K"] for r in rr]))))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    save_json(OUT / "summary.json", summ)


def _dispatch(job):
    fn, kw = job
    return fn(**kw)


if __name__ == "__main__":
    main()
