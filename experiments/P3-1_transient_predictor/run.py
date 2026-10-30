"""P3-1: the transient predictor, open loop (power trace in, temperature trace out).

Models (all calibrated per floorplan, never on test data):
  T1   first-order lag per output (P1-1 step runs)
  T2   ARX, calibrated on the first 20 s of P1-2's excitation trace (main subset only)
  T3   sum of exponentials, M = 2..6 shared time constants (P1-1 step runs)
Every model starts from a cold chip, like HotSpot, and only sees the power trace.
Test sets (HotSpot grid 64x64, Δt = 1 ms):
  short  - one 2 s phase trace on every TA floorplan and HET-A (24)
  long   - two 10 s phase traces on the main subset (shared with P1-2)
  gcc    - EV6 with the real gcc power trace from HotSpot example1 (each 10 ms row held 10 steps)
Metrics over cores: mean and max abs error, peak error, hottest-core accuracy, time per step,
model size.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, datasets
from src.ltp import calibrate as C, bench
from src.ltp.models import SumExp, FirstOrderLag, ARX

OUT = results_dir(__file__)
DT = 1e-3
ARX_ORDER = (2, 2)          # chosen from P1-2
ARX_STATE = "all blocks"    # chosen from P1-2
CAL_STEPS = 20000


def metrics(pred, T, core):
    e = pred[:, core] - T[:, core]
    return dict(mae_K=float(np.abs(e).mean()), max_K=float(np.abs(e).max()),
                peak_err_K=float(np.abs(pred[:, core].max(1) - T[:, core].max(1)).max()),
                hottest_acc=float((pred[:, core].argmax(1) == T[:, core].argmax(1)).mean()))


def gcc_trace(fp):
    lines = (F.REPO / "HotSpot" / "examples" / "example1" / "gcc.ptrace").read_text().split("\n")
    names = lines[0].split()
    rows = np.array([[float(v) for v in l.split()] for l in lines[1:] if l.strip()])
    P = rows[:, [names.index(n) for n in fp.power_names]]
    return np.repeat(P, 10, axis=0)


def build_models(fp, cal, cal_trace):
    G = cal["G"]
    t, Y = C.merged_samples(cal)
    models = {"T1": FirstOrderLag.calibrate(G, t, [Y[:, :, j] for j in range(fp.n_power)],
                                            H.AMBIENT)}
    for M in (2, 3, 4, 5, 6):
        models[f"T3 M={M}"] = SumExp.calibrate(G, t, Y, M, H.AMBIENT)
    if cal_trace is not None:
        out_idx = list(range(len(fp.names))) if ARX_STATE == "all blocks" else fp.power_idx
        arx = ARX.calibrate(G[out_idx], cal_trace["P"], cal_trace["T"][:, out_idx], H.AMBIENT,
                            *ARX_ORDER)
        models[f"T2 ARX{ARX_ORDER}"] = (arx, out_idx)
    return models


def predict(model, fp, P):
    if isinstance(model, tuple):
        m, out_idx = model
        full = np.full((len(P), len(fp.names)), np.nan)
        full[:, out_idx] = m.transient(P)
        return full
    return model.transient(P, DT)


def main():
    ta = F.ta_floorplans() + [F.get("het_a")]
    ev6 = F.get("ev6")
    cals = C.run_calibration_runs_many(ta + [ev6])
    specs = [(fp, "phase", 2000, "short") for fp in ta]
    specs += [(F.get(n), "phase", 10000, f"test{s}") for n in F.MAIN_SUBSET for s in (0, 1)]
    # ARX calibration: first 20 s of P1-2's 60 s excitation trace (main subset only; transient
    # HotSpot runs are the expensive part, and P1-2 already covers trace length)
    specs += [(F.get(n), "excitation", 60000, "cal") for n in F.MAIN_SUBSET]
    specs += [(ev6, "custom", gcc_trace(ev6), "gcc")]
    res = datasets.traces_many(specs, dt=DT)
    tr = {(s[0].name, s[3]): r for s, r in zip(specs, res)}

    rows, timing = [], {}
    for fp in ta + [ev6]:
        cal_trace = tr.get((fp.name, "cal"))
        if cal_trace is not None:
            cal_trace = dict(P=cal_trace["P"][:CAL_STEPS], T=cal_trace["T"][:CAL_STEPS])
        models = build_models(fp, cals[fp.name], cal_trace)
        tests = [k for k in tr if k[0] == fp.name and k[1] != "cal"]
        for (_, salt) in tests:
            P, T = tr[(fp.name, salt)]["P"], tr[(fp.name, salt)]["T"]
            set_ = "short" if salt == "short" else ("gcc" if salt == "gcc" else "long")
            for name, m in models.items():
                pred = predict(m, fp, P)
                mm = m[0] if isinstance(m, tuple) else m
                key = (fp.name, name)
                if key not in timing:
                    fn = (lambda Pk, dt, mm=mm: mm.transient(Pk)) if isinstance(m, tuple) \
                        else (lambda Pk, dt, mm=mm: mm.transient(Pk, dt))
                    timing[key] = bench.time_per_step(fn, P[:2000], DT, repeats=3)
                rows.append(dict(floorplan=fp.name, style=fp.style, test=set_, trace=salt,
                                 model=name, **metrics(pred, T, fp.power_idx),
                                 time_us_per_step=timing[key] * 1e6, size_bytes=mm.size_bytes()))
        print(fp.name, "done")

    save_csv(OUT / "all_results.csv", rows)
    names = ["T1"] + [f"T3 M={M}" for M in (2, 3, 4, 5, 6)] + [f"T2 ARX{ARX_ORDER}"]
    summ = []
    for test in ("short", "long", "gcc"):
        for n in names:
            rr = [r for r in rows if r["test"] == test and r["model"] == n]
            if not rr:
                continue
            summ.append(dict(test=test, model=n, cases=len(rr),
                             mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                             max_K_worst=float(np.max([r["max_K"] for r in rr])),
                             peak_err_K_worst=float(np.max([r["peak_err_K"] for r in rr])),
                             hottest_acc_min=float(np.min([r["hottest_acc"] for r in rr])),
                             time_us_per_step=float(np.median([r["time_us_per_step"] for r in rr])),
                             size_bytes=int(np.median([r["size_bytes"] for r in rr]))))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    hs = np.median([float(r["wall_s"]) / 10000 for k, r in tr.items() if k[1].startswith("test")])
    save_json(OUT / "summary.json", dict(summary=summ, hotspot_s_per_step=float(hs)))

    # figure: one long trace, hottest core, HotSpot vs models
    fp = F.get("s1_fp001")
    P, T = tr[(fp.name, "test0")]["P"], tr[(fp.name, "test0")]["T"]
    ct = tr[(fp.name, "cal")]
    models = build_models(fp, cals[fp.name], dict(P=ct["P"][:CAL_STEPS], T=ct["T"][:CAL_STEPS]))
    k = fp.power_idx[int(np.argmax(T[-1, fp.power_idx]))]
    tt = np.arange(1, len(P) + 1) * DT
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
    ax[0].plot(tt, T[:, k] - 273.15, "k", lw=1.5, label="HotSpot")
    for n in ["T1", "T3 M=2", "T3 M=4", f"T2 ARX{ARX_ORDER}"]:
        pr = predict(models[n], fp, P)
        ax[0].plot(tt, pr[:, k] - 273.15, lw=0.8, label=n)
        ax[1].plot(tt, pr[:, k] - T[:, k], lw=0.8, label=n)
    ax[0].set(ylabel="°C", title=f"{fp.name}, {fp.names[k]}: 10 s test trace from a cold chip")
    ax[1].set(xlabel="time (s)", ylabel="error (K)")
    ax[0].legend(fontsize=7, ncol=5)
    fig.savefig(OUT / "trace_example.png")


if __name__ == "__main__":
    main()
