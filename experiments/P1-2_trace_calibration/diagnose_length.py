"""P1-2 extra: why does ARX (2,2) get worse when the calibration trace grows beyond about 20 s?

Fits ARX (2,2), all-blocks state, on the first K seconds of the 60 s excitation trace for many K and
reports, per floorplan (main subset):
  - open-loop error on the two 10 s test traces (what P1-2 reports),
  - one-step-ahead error (teacher-forced: the model is given HotSpot's own past temperatures) on the
    calibration data and on the test traces (what the least-squares fit actually minimises),
  - the spectral radius of the fitted recursion and the slowest time constant it implies,
  - how busy the calibration trace is (share of steps where any core changes power).

Reads the cached traces in data/generated_traces/npz; G comes from the 8 steady unit runs of each
floorplan (cached in $LTP_RUNS/calib), so it needs HotSpot only for those.

    bash experiments/run.sh P1-2_trace_calibration  (P1-2 itself)
    python3 experiments/P1-2_trace_calibration/diagnose_length.py
"""
import numpy as np

from common import REPO, results_dir, save_csv, save_json, plt
from src.sim import floorplans as F, hotspot as H
from src.ltp import calibrate as C
from src.ltp.models import ARX

OUT = results_dir(__file__)
D = REPO / "data" / "generated_traces" / "npz"
DT, AMB = 1e-3, H.AMBIENT
LENGTHS = [1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 50, 60]


def load(name, kind):
    d = np.load(D / f"trace_{name}_{kind}_dt0.001.npz")
    return d["P"], d["T"] - AMB


def one_step(m, P, x):
    """Teacher-forced one-step-ahead prediction of an ARX (2,2): x[k] from HotSpot's x[k-1], x[k-2]."""
    K = len(P)
    xp = np.vstack([np.zeros((2, x.shape[1])), x])
    Pp = np.vstack([np.zeros((1, P.shape[1])), P])
    return xp[1:K + 1] @ m.A[0].T + xp[0:K] @ m.A[1].T + P @ m.B[0].T + Pp[0:K] @ m.B[1].T


def main():
    rows, activity = [], []
    for name in F.MAIN_SUBSET:
        fp = F.get(name)
        G, core = C.steady_unit_runs(fp)["G"], fp.power_idx
        Pc, xc = load(name, "excitation_60000_cal")
        tests = [load(name, f"phase_10000_test{s}") for s in (0, 1)]
        chg = np.abs(np.diff(Pc, axis=0)).sum(1) > 0
        activity.append(dict(floorplan=name, changes_per_s_0_20=chg[:20000].sum() / 20,
                             changes_per_s_20_60=chg[20000:].sum() / 40,
                             share_steps_changing_0_20=float(chg[:20000].mean()),
                             share_steps_changing_20_60=float(chg[20000:].mean())))
        nb = G.shape[0]
        for K in LENGTHS:
            n = K * 1000
            m = ARX.calibrate(G, Pc[:n], xc[:n] + AMB, AMB, 2, 2)
            comp = np.zeros((2 * nb, 2 * nb))
            comp[:nb] = np.hstack(list(m.A))
            comp[nb:, :-nb] = np.eye(nb)
            rho = float(np.abs(np.linalg.eigvals(comp)).max())
            ol = [np.abs(m.transient(P) - AMB - x)[:, core] for P, x in tests]
            rows.append(dict(
                floorplan=name, cal_s=K,
                open_loop_mae_K=float(np.mean([e.mean() for e in ol])),
                open_loop_max_K=float(max(e.max() for e in ol)),
                open_loop_mae_0_1s=float(np.mean([e[:1000].mean() for e in ol])),
                open_loop_mae_5_10s=float(np.mean([e[5000:].mean() for e in ol])),
                one_step_mae_calibration_K=float(np.abs(one_step(m, Pc[:n], xc[:n]) - xc[:n])[:, core].mean()),
                one_step_mae_test_K=float(np.mean([np.abs(one_step(m, P, x) - x)[:, core].mean()
                                                   for P, x in tests])),
                spectral_radius=rho, slowest_tau_s=float(-DT / np.log(rho)) if rho < 1 else float("inf")))
        print(name, "done")
    save_csv(OUT / "length_diagnostic.csv", rows)
    save_csv(OUT / "length_diagnostic_activity.csv", activity)

    mean = {K: {k: float(np.mean([r[k] for r in rows if r["cal_s"] == K]))
                for k in rows[0] if k not in ("floorplan", "cal_s")} for K in LENGTHS}
    save_json(OUT / "length_diagnostic_mean.json", mean)
    print("cal_s  open-loop  1-step(cal)  1-step(test)  slowest tau")
    for K in LENGTHS:
        m = mean[K]
        print(f"{K:>5}  {m['open_loop_mae_K']:.3f}      {m['one_step_mae_calibration_K']:.5f}     "
              f"{m['one_step_mae_test_K']:.5f}      {m['slowest_tau_s']:.2f}")

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    for name in F.MAIN_SUBSET:
        rr = [r for r in rows if r["floorplan"] == name]
        ax[0].plot([r["cal_s"] for r in rr], [r["open_loop_mae_K"] for r in rr], lw=1, label=name)
    ax[0].plot(LENGTHS, [mean[K]["open_loop_mae_K"] for K in LENGTHS], "k", lw=2, label="mean")
    ax[0].set(xscale="log", xlabel="calibration trace length (s)", ylim=(0, 0.7),
              ylabel="open-loop error on 10 s test traces (K)", title="what we test: open loop")
    ax[0].legend(fontsize=7)
    ax[1].plot(LENGTHS, [mean[K]["one_step_mae_calibration_K"] * 1e3 for K in LENGTHS], "o-",
               label="one-step, on the calibration data")
    ax[1].plot(LENGTHS, [mean[K]["one_step_mae_test_K"] * 1e3 for K in LENGTHS], "s-",
               label="one-step, on the test traces")
    ax[1].set(xscale="log", xlabel="calibration trace length (s)", ylabel="one-step error (mK)",
              title="what the fit minimises: one step ahead")
    ax[1].legend(fontsize=7)
    fig.savefig(OUT / "length_diagnostic.png")


if __name__ == "__main__":
    main()
