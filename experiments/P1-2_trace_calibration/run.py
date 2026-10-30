"""P1-2: calibration from one trace (model T2, ARX), and how long that trace must be.

Main subset. One 60 s excitation trace per floorplan (Δt = 1 ms, every core switching between
random levels in its TA range, phases 1 ms to 5 s), simulated by HotSpot from a cold chip.
ARX models are fitted on its first 1, 5, 20 and 60 s, with the steady gain fixed to G (from P1-1),
for two state choices:
  all blocks  - the state is every block of the power layer (cores + FILL)
  cores only  - only the core temperatures (what on-chip sensors would give)
and orders (na, nb) = (1, 1), (2, 2), (3, 3). They are tested open loop (only power as input)
on two unseen 10 s phase traces, against HotSpot. T3 (M = 4, from P1-1's step runs) is shown
for reference.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, datasets
from src.ltp import calibrate as C
from src.ltp.models import ARX, SumExp

OUT = results_dir(__file__)
DT = 1e-3
CAL_S = [1, 5, 20, 60]
TEST_S = 10
ORDERS = [(1, 1), (2, 2), (3, 3)]


def main():
    fps = [F.get(n) for n in F.MAIN_SUBSET]
    specs = [(fp, "excitation", CAL_S[-1] * 1000, "cal") for fp in fps] + \
            [(fp, "phase", TEST_S * 1000, f"test{s}") for fp in fps for s in (0, 1)]
    res = datasets.traces_many(specs, dt=DT)          # cached; shared with P3/P4
    cal_P = {fp.name: r["P"] for fp, r in zip(fps, res[:len(fps)])}
    cal_T = {fp.name: r for fp, r in zip(fps, res[:len(fps)])}
    test_P = {(fp.name, s): r["P"] for (fp, _, _, salt), r in zip(specs[len(fps):], res[len(fps):])
              for s in [int(salt[-1])]}
    test_T = {(fp.name, s): r for (fp, _, _, salt), r in zip(specs[len(fps):], res[len(fps):])
              for s in [int(salt[-1])]}
    cals = C.run_calibration_runs_many(fps)          # cached from P1-1

    rows = []
    for fp in fps:
        G = cals[fp.name]["G"]
        core = fp.power_idx
        t, Y = C.merged_samples(cals[fp.name])
        t3 = SumExp.calibrate(G, t, Y, 4, H.AMBIENT)
        for s in (0, 1):
            Tm = t3.transient(test_P[(fp.name, s)], DT)[:, core]
            Th = test_T[(fp.name, s)]["T"][:, core]
            rows.append(dict(floorplan=fp.name, state="-", model="T3 M=4 (P1-1)", na=0, nb=0,
                             cal_s=0, test=s, mae_K=float(np.abs(Tm - Th).mean()),
                             max_K=float(np.abs(Tm - Th).max()), size_bytes=t3.size_bytes(),
                             stable=True))
        for state, out_idx in (("all blocks", list(range(len(fp.names)))), ("cores only", core)):
            Gs = G[out_idx]
            for na, nb in ORDERS:
                for cs in CAL_S:
                    K = cs * 1000
                    m = ARX.calibrate(Gs, cal_P[fp.name][:K], cal_T[fp.name]["T"][:K, out_idx],
                                      H.AMBIENT, na=na, nb=nb)
                    # stability of the open-loop recursion: spectral radius of the companion matrix
                    n = len(out_idx)
                    comp = np.zeros((na * n, na * n))
                    comp[:n] = np.hstack(list(m.A))
                    if na > 1:
                        comp[n:, :-n] = np.eye((na - 1) * n)
                    rho = float(np.abs(np.linalg.eigvals(comp)).max())
                    for s in (0, 1):
                        Tm = m.transient(test_P[(fp.name, s)])
                        ci = [out_idx.index(c) for c in core]
                        err = Tm[:, ci] - test_T[(fp.name, s)]["T"][:, core]
                        err = np.where(np.isfinite(err), err, 1e3)
                        rows.append(dict(floorplan=fp.name, state=state, model="T2 ARX",
                                         na=na, nb=nb, cal_s=cs, test=s,
                                         mae_K=float(np.abs(err).mean()),
                                         max_K=float(np.abs(err).max()),
                                         size_bytes=m.size_bytes(), stable=rho < 1,
                                         spectral_radius=rho))
        print(fp.name, "done")

    save_csv(OUT / "all_results.csv", [{k: r.get(k, "") for k in rows[-1]} for r in rows])
    # summary: worst over floorplans and test traces, per (state, order, length)
    summ = []
    for state in ("all blocks", "cores only"):
        for na, nb in ORDERS:
            for cs in CAL_S:
                rr = [r for r in rows if r["state"] == state and r["na"] == na and r["cal_s"] == cs]
                summ.append(dict(state=state, order=f"({na},{nb})", cal_s=cs,
                                 mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                                 max_K_worst=float(np.max([r["max_K"] for r in rr])),
                                 all_stable=all(r["stable"] for r in rr),
                                 size_bytes_max=max(r["size_bytes"] for r in rr)))
    rr = [r for r in rows if r["model"].startswith("T3")]
    summ.append(dict(state="-", order="T3 M=4", cal_s=0,
                     mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                     max_K_worst=float(np.max([r["max_K"] for r in rr])), all_stable=True,
                     size_bytes_max=max(r["size_bytes"] for r in rr)))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    save_json(OUT / "summary.json", dict(summary=summ,
                                         hotspot_cal_trace_s={n: cal_T[n]["wall_s"] for n in cal_T}))

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, state in zip(axes, ("all blocks", "cores only")):
        for na, nb in ORDERS:
            ss = [s for s in summ if s["state"] == state and s["order"] == f"({na},{nb})"]
            fin = lambda v: v if np.isfinite(v) and v < 1e3 else np.nan   # noqa: E731
            ax.loglog([s["cal_s"] for s in ss], [fin(s["mae_K_mean"]) for s in ss], "o-",
                      label=f"ARX ({na},{nb}), mean abs error")
            ax.loglog([s["cal_s"] for s in ss], [fin(s["max_K_worst"]) for s in ss], "x:",
                      color=ax.lines[-1].get_color(), label=f"ARX ({na},{nb}), worst max error")
        t3s = summ[-1]
        ax.axhline(t3s["mae_K_mean"], color="k", lw=0.8, label="T3 M=4, mean abs error")
        ax.axhline(t3s["max_K_worst"], color="k", ls=":", lw=0.8, label="T3 M=4, worst max error")
        ax.set(xlabel="calibration trace length (s)", title=f"ARX state: {state}",
               ylim=(0.03, 100))
    axes[0].set_ylabel("open-loop test error, cores (K)\n(missing points: unstable model)")
    axes[1].legend(fontsize=6)
    fig.savefig(OUT / "error_vs_trace_length.png")


if __name__ == "__main__":
    main()
