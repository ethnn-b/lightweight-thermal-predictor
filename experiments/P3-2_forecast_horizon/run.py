"""P3-2: forecasting h steps ahead from sensor readings (the curve DTM depends on).

At many start points k0 of the two 10 s test traces on the main subset, a model gets the
measured core temperatures up to k0 (HotSpot stands in for the sensors) and the planned power
for k0+1 .. k0+h, and forecasts the core temperatures at k0+h, for h = 1, 10, 100, 1000 steps
(1 ms to 1 s). Models:
  T0 persistence           T(k0+h) = T(k0)
  T1 from sensors          first-order lag started at the measured temperatures
  T3 anchored (M = 4)      T3 run on the power history, shifted to match the sensors at k0
  T3 open loop (M = 4)     T3 on the power alone, no sensors (= P3-1)
  T2 ARX from sensors      cores-only ARX (2,2) started from the last measured temperatures
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, datasets
from src.ltp import calibrate as C, bench
from src.ltp.models import SumExp, FirstOrderLag, ARX
from src.ltp.predictor import Predictor

OUT = results_dir(__file__)
DT = 1e-3
HORIZONS = [1, 10, 100, 1000]
STARTS = np.arange(100, 9000, 25)


def main():
    fps = [F.get(n) for n in F.MAIN_SUBSET]
    cals = C.run_calibration_runs_many(fps)
    specs = [(fp, "phase", 10000, f"test{s}") for fp in fps for s in (0, 1)]
    specs += [(fp, "excitation", 60000, "cal") for fp in fps]
    res = datasets.traces_many(specs, dt=DT)
    tr = {(s[0].name, s[3]): r for s, r in zip(specs, res)}
    rows, per_point = [], []
    for fp in fps:
        core = fp.power_idx
        cal = cals[fp.name]
        G = cal["G"]
        t, Y = C.merged_samples(cal)
        t3 = SumExp.calibrate(G, t, Y, 4, H.AMBIENT)
        t1 = FirstOrderLag.calibrate(G, t, [Y[:, :, j] for j in range(fp.n_power)], H.AMBIENT)
        ct = tr[(fp.name, "cal")]
        arx = ARX.calibrate(G[core], ct["P"][:20000], ct["T"][:20000][:, core], H.AMBIENT, 2, 2)
        a1 = np.exp(-DT / t1.tau[core])
        for s in (0, 1):
            P, T = tr[(fp.name, f"test{s}")]["P"], tr[(fp.name, f"test{s}")]["T"][:, core]
            Tm = t3.transient(P, DT)[:, core]                    # T3 open loop, whole trace
            hmax = max(HORIZONS)
            ks = STARTS[STARTS + hmax < len(P)]
            # T1 and ARX: propagate all start points at once
            x1 = T[ks] - H.AMBIENT
            xa = [T[ks] - H.AMBIENT, T[ks - 1] - H.AMBIENT]       # x[k0], x[k0-1]
            pa = [P[ks], P[ks - 1]]
            fc = {name: {} for name in ["T0 persistence", "T1 from sensors", "T3 anchored",
                                        "T3 open loop", "T2 ARX from sensors"]}
            for h in range(1, hmax + 1):
                p = P[ks + h]
                x1 = a1 * x1 + (1 - a1) * (p @ G[core].T)
                pa = [p, pa[0]]
                xn = sum(xa[l] @ arx.A[l].T for l in range(2)) + sum(pa[l] @ arx.B[l].T for l in range(2))
                xa = [xn, xa[0]]
                if h in HORIZONS:
                    fc["T0 persistence"][h] = T[ks]
                    fc["T1 from sensors"][h] = H.AMBIENT + x1
                    fc["T3 anchored"][h] = T[ks] + Tm[ks + h] - Tm[ks]
                    fc["T3 open loop"][h] = Tm[ks + h]
                    fc["T2 ARX from sensors"][h] = H.AMBIENT + xn
            for name, d in fc.items():
                for h, pred in d.items():
                    e = pred - T[ks + h]
                    rows.append(dict(floorplan=fp.name, trace=s, model=name, horizon_steps=h,
                                     horizon_ms=h * DT * 1e3, mae_K=float(np.abs(e).mean()),
                                     max_K=float(np.abs(e).max()),
                                     p99_K=float(np.percentile(np.abs(e), 99))))
        print(fp.name, "done")

    # cost of one forecast call (10 steps ahead) with the shipped predictor
    fp = fps[0]
    cal = cals[fp.name]
    t, Y = C.merged_samples(cal)
    t3 = SumExp.calibrate(cal["G"], t, Y, 4, H.AMBIENT)
    pr = Predictor(fp.names, fp.power_names, H.AMBIENT, cal["G"], t3.A, t3.tau)
    P = tr[(fp.name, "test0")]["P"]
    z = pr.run_state(P[:500], DT)
    T_now = tr[(fp.name, "test0")]["T"][499]
    t_fc = {h: bench.time_call(pr.forecast, [(T_now, z, P[500:500 + h], DT)], repeats=2000,
                               warmup=100)[0] for h in (10, 100)}

    save_csv(OUT / "all_results.csv", rows)
    summ = []
    for name in ["T0 persistence", "T1 from sensors", "T3 open loop", "T3 anchored",
                 "T2 ARX from sensors"]:
        for h in HORIZONS:
            rr = [r for r in rows if r["model"] == name and r["horizon_steps"] == h]
            summ.append(dict(model=name, horizon_ms=h * DT * 1e3,
                             mae_K=float(np.mean([r["mae_K"] for r in rr])),
                             p99_K_worst=float(np.max([r["p99_K"] for r in rr])),
                             max_K_worst=float(np.max([r["max_K"] for r in rr]))))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    save_json(OUT / "summary.json", dict(summary=summ,
                                         forecast_call_us={h: v * 1e6 for h, v in t_fc.items()}))
    print({h: f"{v * 1e6:.0f} us" for h, v in t_fc.items()})

    fig, ax = plt.subplots(figsize=(6, 4))
    for name in ["T0 persistence", "T1 from sensors", "T3 open loop", "T3 anchored",
                 "T2 ARX from sensors"]:
        ss = [s for s in summ if s["model"] == name]
        ax.loglog([s["horizon_ms"] for s in ss], [max(s["max_K_worst"], 1e-6) for s in ss], "o-",
                  label=name)
    ax.set(xlabel="forecast horizon (ms)", ylabel="worst max abs error, cores (K)",
           title="forecast error vs horizon (main subset, 2 traces each)")
    ax.legend(fontsize=7)
    fig.savefig(OUT / "error_vs_horizon.png")


if __name__ == "__main__":
    main()
