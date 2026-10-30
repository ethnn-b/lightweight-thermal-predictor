"""P0-2: is HotSpot (grid model, TA layer stack, leakage off) linear in power?

Checks, on the four main-subset floorplans:
  steady    - scaling: rise(s*P) = s*rise(P) for s = 0.5, 2, 3; zero power gives ambient;
            - superposition: rise(A + B) = rise(A) + rise(B) (A = big cores only, B = little only)
            - 1 W vs 10 W unit steps give the same influence column (output precision check)
  transient - the same scaling and superposition on a 500-step (0.5 s) phase trace from cold.
If all of these hold to ~1e-5 K, the predictor models S1/T2/T3 can be exact, and any later error
is a bug or a calibration problem rather than physics.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, powergen
from src.sim.parallel import pmap

OUT = results_dir(__file__)
AMB = H.AMBIENT
G = "P0-2"


def steady_T(fp_name, p):
    fp = F.get(fp_name)
    return H.steady(fp, p, group=G, keep=False)["T"]


def trans_T(fp_name, P, dt):
    fp = F.get(fp_name)
    return H.transient(fp, P, dt, group=G, keep=False)["T"]


def main():
    rows, trans_rows = [], []
    for name in F.MAIN_SUBSET:
        fp = F.get(name)
        P = fp.nominal_power()
        big = np.array([t == "big" for t in fp.power_types], float)
        A, B = P * big, P * (1 - big)
        j = 2                                  # a little core, for the unit-step check
        e1 = np.zeros(fp.n_power); e1[j] = 1.0
        cases = {"P": P, "0.5P": 0.5 * P, "2P": 2 * P, "3P": 3 * P, "zero": 0 * P,
                 "A": A, "B": B, "1W": e1, "10W": 10 * e1}
        res = dict(zip(cases, pmap(steady_T, [dict(fp_name=name, p=v) for v in cases.values()])))
        rise = {k: v - AMB for k, v in res.items()}
        rows.append(dict(
            floorplan=name,
            peak_C=float(res["P"].max() - 273.15),
            scale_0p5_maxerr_K=float(np.abs(rise["0.5P"] - 0.5 * rise["P"]).max()),
            scale_2_maxerr_K=float(np.abs(rise["2P"] - 2 * rise["P"]).max()),
            scale_3_maxerr_K=float(np.abs(rise["3P"] - 3 * rise["P"]).max()),
            zero_maxdev_from_ambient_K=float(np.abs(rise["zero"]).max()),
            superposition_maxerr_K=float(np.abs(rise["P"] - rise["A"] - rise["B"]).max()),
            unit_1W_vs_10W_maxerr_K=float(np.abs(rise["1W"] - rise["10W"] / 10).max()),
        ))

        # transient: 500 steps of 1 ms from a cold chip
        Ptr = powergen.phase_trace(fp, 500, seed=1, max_phase=200)
        btr = Ptr * big
        tcases = {"P": Ptr, "2P": 2 * Ptr, "A": btr, "B": Ptr - btr}
        tres = dict(zip(tcases, pmap(trans_T, [dict(fp_name=name, P=v, dt=1e-3)
                                               for v in tcases.values()])))
        tr = {k: v - AMB for k, v in tres.items()}
        trans_rows.append(dict(
            floorplan=name,
            scale_2_maxerr_K=float(np.abs(tr["2P"] - 2 * tr["P"]).max()),
            superposition_maxerr_K=float(np.abs(tr["P"] - tr["A"] - tr["B"]).max()),
            max_rise_K=float(tr["P"].max()),
        ))
        if name == F.MAIN_SUBSET[0]:
            t = np.arange(1, 501)
            fig, ax = plt.subplots(1, 2, figsize=(9, 3.2))
            k = int(np.argmax(tr["P"][-1]))
            ax[0].plot(t, tr["P"][:, k], label="rise(P)")
            ax[0].plot(t, tr["A"][:, k] + tr["B"][:, k], "--", label="rise(A) + rise(B)")
            ax[0].plot(t, tr["2P"][:, k] / 2, ":", label="rise(2P) / 2")
            ax[0].set(xlabel="step (1 ms)", ylabel="temperature rise (K)",
                      title=f"{name}, {fp.names[k]}")
            ax[0].legend()
            ax[1].semilogy(t, np.abs(tr["P"] - tr["A"] - tr["B"]).max(1) + 1e-9, label="superposition")
            ax[1].semilogy(t, np.abs(tr["2P"] - 2 * tr["P"]).max(1) + 1e-9, label="scaling x2")
            ax[1].set(xlabel="step (1 ms)", ylabel="max |error| over blocks (K)",
                      title="deviation from linearity")
            ax[1].legend()
            fig.savefig(OUT / "transient_linearity.png")

    save_csv(OUT / "steady_linearity.csv", rows)
    save_csv(OUT / "transient_linearity.csv", trans_rows)
    print(md_table(rows, "{:.3g}"))
    print()
    print(md_table(trans_rows, "{:.3g}"))
    save_json(OUT / "summary.json", dict(
        steady_worst_K=max(max(v for k, v in r.items() if k.endswith("_K")) for r in rows),
        transient_worst_K=max(max(r["scale_2_maxerr_K"], r["superposition_maxerr_K"])
                              for r in trans_rows)))


if __name__ == "__main__":
    main()
