"""Extended validation, part 3: T3 (M = 4) heatmaps against HotSpot's at several times.

For gen_012 of each style (the floorplans of maps.py) and one 5 s phase trace from a cold chip
(1 ms steps), HotSpot's 64x64 grid map, HotSpot's block averages, T3's prediction and the error
at t = 2.0, 2.5, ..., 5.0 s. One figure per floorplan (rows: the four maps; columns: the times),
plus the T3 error over the whole trace.

HotSpot's -grid_transient_file holds every step (about 1.2 GB for 5000 steps), so each run is
parsed in one pass for the wanted steps and deleted; the snapshots are cached in ~/ltp_runs.

    PYTHONPATH=. python3 experiments/extended_validation/maps_time.py
"""
from pathlib import Path

import numpy as np

from common import results_dir, save_csv, plt
from src.sim import hotspot as H, tagen, powergen
from src.sim.datasets import _seed
from src.sim.parallel import pmap
from src.ltp import calibrate as C
from src.ltp.models import SumExp
from maps import PICK, paint

OUT = results_dir(__file__)
AMB, DT, STEPS, ROWS = H.AMBIENT, 1e-3, 5000, 64
TIMES = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
KS = [int(round(t / DT)) - 1 for t in TIMES]          # row k of a ttrace is the end of step k
CACHE = H.RUNS / "extended_maps"


def grid_snapshots(path, ks, rows=ROWS):
    """Layer 0 (die) maps of the samples ks of a -grid_transient_file, read in one pass."""
    want, out, sample, buf = set(ks), {}, -1, None
    with open(path) as f:
        for line in f:
            if line.startswith("Layer"):
                if buf is not None:
                    out[sample] = np.array(buf).reshape(rows, rows); buf = None
                if line.startswith("Layer 0"):
                    sample += 1
                    if sample in want:
                        buf = []
                continue
            if buf is not None:
                parts = line.split()
                if len(parts) == 2:
                    buf.append(float(parts[1]))
    if buf is not None:
        out[sample] = np.array(buf).reshape(rows, rows)
    return out, sample + 1


def job(fp, P):
    path = CACHE / f"snapshots_{fp.name}_phase{STEPS}.npz"
    if path.exists():
        d = dict(np.load(path))
        return dict(T=d["T"], grids=d["grids"], n=int(d["n"]))
    res = H.transient(fp, P, DT, group="extended_maps", model="grid", rows=ROWS, keep=True,
                      extra={"grid_transient_file": "out.grid.ttrace"})
    snaps, n = grid_snapshots(Path(res["dir"]) / "out.grid.ttrace", KS)
    H._cleanup(res["dir"])
    grids = np.array([snaps[k] for k in KS])
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(path, T=res["T"], grids=grids, n=n, P=P)
    return dict(T=res["T"], grids=grids, n=n)


def main():
    fps = [f for f in tagen.generated(13) if f.name in PICK]
    cals = C.run_calibration_runs_many(fps)
    Ps = [powergen.phase_trace(fp, STEPS, seed=_seed(fp.name, "phase/maps_time")) for fp in fps]
    hs = pmap(job, [dict(fp=fp, P=P) for fp, P in zip(fps, Ps)])
    rows = []
    fig_e, ax_e = plt.subplots(1, 4, figsize=(14, 3.2), sharey=True, layout="constrained")
    for fp, P, h, axe in zip(fps, Ps, hs, ax_e):
        # one grid sample per step (no extra t = 0 sample), so grid sample k is ttrace row k
        assert h["n"] == STEPS == len(h["T"]), (fp.name, h["n"])
        cal, core = cals[fp.name], fp.power_idx
        t, Y = C.merged_samples(cal)
        t3 = SumExp.calibrate(cal["G"], t, Y, 4, AMB)
        pred_all, T = t3.transient(P, DT), h["T"]
        lo = min(h["grids"].min(), pred_all[KS].min()) - 273.15
        hi = max(h["grids"].max(), pred_all[KS].max()) - 273.15
        m = max(np.abs(pred_all[KS] - T[KS]).max(), 1e-9)
        W, Hd = fp.die
        fig, axes = plt.subplots(4, len(TIMES), figsize=(2.6 * len(TIMES) + 1.5,
                                                                     4 * 2.5 * Hd / W + 1.6),
                                 layout="constrained")
        for c, (tt, k, g) in enumerate(zip(TIMES, KS, h["grids"])):
            truth, pred = T[k] - 273.15, pred_all[k] - 273.15
            im = axes[0, c].imshow(g - 273.15, extent=[0, W * 1e3, 0, Hd * 1e3], cmap="inferno",
                                   vmin=lo, vmax=hi)
            paint(axes[1, c], fp, truth, lo, hi); paint(axes[2, c], fp, pred, lo, hi)
            e_im = paint(axes[3, c], fp, pred - truth, -m, m, cmap="coolwarm")
            axes[0, c].set_title(f"t = {tt:g} s", fontsize=10)
            for a in axes[:, c]:
                a.grid(False); a.tick_params(labelsize=7)
            err = pred[core] - truth[core]
            rows.append(dict(floorplan=fp.name, t_s=tt, hotspot_peak_cell_C=float(g.max() - 273.15),
                             hotspot_core_max_C=float(truth[core].max()),
                             t3_core_max_C=float(pred[core].max()),
                             t3_mae_K=float(np.abs(err).mean()), t3_max_abs_err_K=float(np.abs(err).max())))
        for r, lab in enumerate(("HotSpot grid 64x64", "HotSpot, block average", "T3 (M = 4)",
                                 "T3 minus HotSpot")):
            axes[r, 0].set_ylabel(f"{lab}\nmm", fontsize=9)
        fig.colorbar(im, ax=axes[:3, :], shrink=0.6, pad=0.01, label="°C")
        fig.colorbar(e_im, ax=axes[3, :], shrink=0.9, pad=0.01, label="K")
        fig.suptitle(f"{fp.name}: T3 (M = 4) against HotSpot over time (5 s phase trace, 1 ms steps)")
        fig.savefig(OUT / f"heatmaps_t3_time_{fp.name}.png", dpi=110)
        plt.close(fig)
        e = np.abs(pred_all[:, core] - T[:, core]).max(1)
        tt = (np.arange(STEPS) + 1) * DT
        axe.plot(tt, e, lw=0.8)
        axe.plot(TIMES, e[KS], "o", ms=4, color="C3")
        axe.set(title=fp.name, xlabel="time (s)")
    ax_e[0].set_ylabel("T3 worst core error (K)")
    fig_e.savefig(OUT / "t3_error_over_time.png")
    save_csv(OUT / "heatmaps_time_summary.csv", rows)
    for x in rows:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in x.items()})


if __name__ == "__main__":
    main()
