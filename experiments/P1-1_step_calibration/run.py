"""P1-1: calibration by unit-step runs (models S1, T1, T3).

For every TA floorplan (23) and HET-A: 3N HotSpot runs (N steady unit runs, N fine and N coarse
unit-step transients), then fit
  S1  influence matrix G (exact by construction),
  T1  one time constant per output,
  T3  M shared time constants, M = 1..6.
Outputs: model files, calibration cost, fit error on the calibration runs themselves, and
figures of G and of the step responses. Test-set accuracy is measured later (P2-1, P3-1).
"""
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H
from src.ltp import calibrate as C
from src.ltp.models import SteadyG, FirstOrderLag, SumExp

OUT = results_dir(__file__)
MODELS = OUT / "models"
MODELS.mkdir(exist_ok=True)
MS = [1, 2, 3, 4, 5, 6]


def fit_errors(model_step, cal, P):
    """Max |error| (K) of a model's response to a step to power vector P, over the full fine
    trace (0-2 s, every 1 ms) and the coarse trace after 2 s."""
    out = {}
    for key, tk in (("fine", "t_fine"), ("coarse", "t_coarse")):
        t = cal[tk]
        sel = t > C.T_SWITCH if key == "coarse" else slice(None)
        Y = cal[f"Y_{key}"][sel] @ P                       # HotSpot rise for the step to P
        Ym = model_step(t[sel]) @ P
        out[key] = float(np.abs(Ym - Y).max())
    return max(out.values())


def main():
    fps = F.ta_floorplans() + [F.get("het_a")]
    t0 = time.perf_counter()
    cals = C.run_calibration_runs_many(fps)
    print(f"HotSpot calibration runs done in {time.perf_counter() - t0:.0f} s")

    rows, fits = [], []
    for fp in fps:
        cal = cals[fp.name]
        G = cal["G"]
        t, Y = C.merged_samples(cal)
        Pn = fp.nominal_power()
        s1 = SteadyG(G, H.AMBIENT)
        s1.save(MODELS / f"{fp.name}_S1.npz", names=fp.names, power_names=fp.power_names)

        tf = time.perf_counter()
        t1 = FirstOrderLag.calibrate(G, t, [Y[:, :, j] for j in range(fp.n_power)], H.AMBIENT)
        t1.save(MODELS / f"{fp.name}_T1.npz", names=fp.names, power_names=fp.power_names)
        t1_err = fit_errors(lambda tt: np.stack([G * (1 - np.exp(-x / t1.tau))[:, None]
                                                 for x in tt]), cal, Pn)
        fit_s = {"T1": time.perf_counter() - tf}
        t3 = {}
        for M in MS:
            tf = time.perf_counter()
            t3[M] = SumExp.calibrate(G, t, Y, M, H.AMBIENT)
            fit_s[f"T3_M{M}"] = time.perf_counter() - tf
            t3[M].save(MODELS / f"{fp.name}_T3_M{M}.npz", names=fp.names,
                       power_names=fp.power_names)
        errs = {M: fit_errors(t3[M].step_response, cal, Pn) for M in MS}
        for M in MS:
            fits.append(dict(floorplan=fp.name, style=fp.style, model=f"T3 M={M}",
                             fit_maxerr_nominal_step_K=errs[M], size_bytes=t3[M].size_bytes(),
                             fit_s=fit_s[f"T3_M{M}"],
                             taus_s=" ".join(f"{x:.3g}" for x in t3[M].tau)))
        fits.append(dict(floorplan=fp.name, style=fp.style, model="T1",
                         fit_maxerr_nominal_step_K=t1_err, size_bytes=t1.size_bytes(),
                         fit_s=fit_s["T1"], taus_s=""))

        core = fp.power_idx
        types = fp.power_types
        Gc = G[core]
        big = [i for i, x in enumerate(types) if x == "big"]
        lit = [i for i, x in enumerate(types) if x == "little"]
        off = Gc[~np.eye(len(core), dtype=bool)]
        rows.append(dict(
            floorplan=fp.name, style=fp.style, N=fp.n_power,
            hotspot_runs=int(3 * fp.n_power),
            hotspot_cpu_s=float(cal["hotspot_s_steady"].sum() + cal["hotspot_s_transient"].sum()),
            hotspot_cpu_s_S1_only=float(cal["hotspot_s_steady"].sum()),
            G_self_big_KperW=float(np.mean([Gc[i, i] for i in big])) if big else np.nan,
            G_self_little_KperW=float(np.mean([Gc[i, i] for i in lit])) if lit else np.nan,
            G_offdiag_min_KperW=float(off.min()), G_offdiag_max_KperW=float(off.max()),
            S1_bytes_cores=int(Gc.nbytes), S1_bytes_all_blocks=int(G.nbytes),
            T1_fit_maxerr_K=t1_err, T3_M3_fit_maxerr_K=errs[3], T3_M4_fit_maxerr_K=errs[4],
            T3_M6_fit_maxerr_K=errs[6],
        ))
        print(f"{fp.name}: T1 {t1_err:.3f} K, T3 " +
              ", ".join(f"M{M} {errs[M]:.4f}" for M in MS))

    save_csv(OUT / "calibration_summary.csv", rows)
    save_csv(OUT / "fit_errors.csv", fits)
    keys = ["floorplan", "hotspot_runs", "hotspot_cpu_s", "G_self_big_KperW",
            "G_self_little_KperW", "G_offdiag_max_KperW", "T1_fit_maxerr_K",
            "T3_M3_fit_maxerr_K", "T3_M4_fit_maxerr_K", "T3_M6_fit_maxerr_K"]
    print(md_table([{k: r[k] for k in keys} for r in rows], "{:.3g}"))

    # fit error vs M, over all floorplans
    agg = []
    for M in MS:
        e = [f["fit_maxerr_nominal_step_K"] for f in fits if f["model"] == f"T3 M={M}"]
        agg.append(dict(model=f"T3 M={M}", median_K=float(np.median(e)), worst_K=float(np.max(e)),
                        bytes_TA=int(np.median([f["size_bytes"] for f in fits
                                                if f["model"] == f"T3 M={M}"]))))
    e = [f["fit_maxerr_nominal_step_K"] for f in fits if f["model"] == "T1"]
    agg.append(dict(model="T1", median_K=float(np.median(e)), worst_K=float(np.max(e)),
                    bytes_TA=int(np.median([f["size_bytes"] for f in fits if f["model"] == "T1"]))))
    save_csv(OUT / "fit_error_vs_M.csv", agg)
    print(md_table(agg, "{:.3g}"))
    save_json(OUT / "summary.json", dict(fit_error_vs_M=agg,
                                         total_hotspot_cpu_s=sum(r["hotspot_cpu_s"] for r in rows)))
    figures(fps, cals)


def figures(fps, cals):
    # G heat maps (cores only) for one floorplan per style
    sel = F.MAIN_SUBSET
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.4))
    for ax, n in zip(axes, sel):
        fp = F.get(n)
        Gc = cals[n]["G"][fp.power_idx]
        im = ax.imshow(Gc, cmap="viridis")
        lab = [f"{x.split('_')[1]}{t[0].upper()}" for x, t in zip(fp.power_names, fp.power_types)]
        ax.set_xticks(range(len(lab)), lab); ax.set_yticks(range(len(lab)), lab)
        ax.set(title=n, xlabel="heated core j", ylabel="core i"); ax.grid(False)
        fig.colorbar(im, ax=ax, shrink=0.8, label="G_ij (K/W)")
    fig.savefig(OUT / "G_heatmaps.png")

    # self-heating and coupling vs core type / distance, all TA floorplans
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    for fp in fps[:23]:
        Gc = cals[fp.name]["G"][fp.power_idx]
        bl = [fp.blocks[i] for i in fp.power_idx]
        cx = np.array([b.x + b.w / 2 for b in bl]); cy = np.array([b.y + b.h / 2 for b in bl])
        for i, t in enumerate(fp.power_types):
            ax[0].scatter(1e3 * min(cx[i] - bl[i].w / 2, cy[i] - bl[i].h / 2,
                                    fp.die[0] - cx[i] - bl[i].w / 2, fp.die[1] - cy[i] - bl[i].h / 2),
                          Gc[i, i], c="C0" if t == "big" else "C1", s=10)
            for j in range(len(bl)):
                if i != j:
                    ax[1].scatter(1e3 * np.hypot(cx[i] - cx[j], cy[i] - cy[j]), Gc[i, j],
                                  c="C2", s=4, alpha=0.4)
    ax[0].scatter([], [], c="C0", label="big"); ax[0].scatter([], [], c="C1", label="little")
    ax[0].set(xlabel="distance from core edge to die edge (mm)", ylabel="self-heating G_ii (K/W)",
              title="self-heating: core type and position"); ax[0].legend()
    ax[1].set(xlabel="centre-to-centre distance (mm)", ylabel="coupling G_ij (K/W)",
              title="coupling between cores, all 23 floorplans")
    fig.savefig(OUT / "G_vs_geometry.png")

    # step responses with fits, one floorplan
    n = "s4_fp001"
    fp = F.get(n)
    cal = cals[n]
    G = cal["G"]
    t, Y = C.merged_samples(cal)
    t1 = FirstOrderLag.calibrate(G, t, [Y[:, :, j] for j in range(fp.n_power)], H.AMBIENT)
    t3 = SumExp.calibrate(G, t, Y, 4, H.AMBIENT)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    for ax, j in zip(axes, [0, 2]):
        i = fp.power_idx[j]
        ax.semilogx(cal["t_fine"], cal["Y_fine"][:, i, j], "k", lw=2, label="HotSpot, 1 ms steps")
        ax.semilogx(cal["t_coarse"], cal["Y_coarse"][:, i, j], "grey", lw=2, label="HotSpot, 20 ms steps")
        tt = np.logspace(-3, 2, 300)
        ax.semilogx(tt, t3.step_response(tt)[:, i, j], "C1--", label="T3 (M = 4)")
        ax.semilogx(tt, G[i, j] * (1 - np.exp(-tt / t1.tau[i])), "C0:", label="T1")
        k = fp.power_idx[1 - j if j == 0 else 3]
        ax.semilogx(cal["t_fine"], cal["Y_fine"][:, k, j], "k", lw=1)
        ax.semilogx(cal["t_coarse"], cal["Y_coarse"][:, k, j], "grey", lw=1)
        ax.semilogx(tt, t3.step_response(tt)[:, k, j], "C1--", lw=1)
        ax.set(xlabel="time after a 1 W step (s)", ylabel="temperature rise (K)",
               title=f"{n}: 1 W in {fp.power_names[j]} ({fp.power_types[j]})\n"
                     f"thick = that core, thin = {fp.names[k]}")
        ax.legend(fontsize=7)
    fig.savefig(OUT / "step_response_fits.png")


if __name__ == "__main__":
    main()
