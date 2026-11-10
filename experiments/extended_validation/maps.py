"""Extended validation, part 2: predicted heatmaps against HotSpot's, one floorplan per style.

For gen_012 of each style (a new floorplan, not picked by its error) and one random steady power
vector from the test set:
  - HotSpot's 64x64 grid map (what the TA's setup produces, with hot spots inside blocks);
  - HotSpot's block averages (what S1 is trained to predict), painted per block;
  - S1's prediction, painted per block;
  - S1 minus HotSpot block averages.
And for the same floorplans, T3's transient prediction against HotSpot on the 2 s phase trace.
Calibration data comes from the cache written by run.py (the same 24 runs per floorplan).

    PYTHONPATH=. python3 experiments/extended_validation/maps.py
"""
from pathlib import Path

import numpy as np

from common import results_dir, save_csv, plt
from src.sim import hotspot as H, datasets, tagen
from src.ltp import calibrate as C
from src.ltp.models import SteadyG, SumExp

OUT = results_dir(__file__)
AMB, DT = H.AMBIENT, 1e-3
PICK = ["g1_gen012", "g2_gen012", "g3_gen012", "g4_gen012"]
VEC = 2                                    # first random vector of the steady test set


def paint(ax, fp, T, vmin, vmax, cmap="inferno"):
    W, Hd = fp.die
    norm = plt.Normalize(vmin, vmax)
    cm = plt.get_cmap(cmap)
    for b, t in zip(fp.blocks, T):
        ax.add_patch(plt.Rectangle((b.x * 1e3, b.y * 1e3), b.w * 1e3, b.h * 1e3,
                                   fc=cm(norm(t)), ec="none"))
    ax.set_xlim(0, W * 1e3); ax.set_ylim(0, Hd * 1e3); ax.set_aspect("equal")
    return plt.cm.ScalarMappable(norm, cm)


def last_grid(path, rows=64, layer=0):
    """The rows x rows map of one layer at the last sample of a -grid_transient_file (read from the
    end; the file is about 0.5 GB for 2000 steps)."""
    n = 4 * (rows * rows + 1)                       # 4 layers per sample (die, TIM, spreader, sink)
    with open(path, "rb") as f:
        f.seek(0, 2); f.seek(max(0, f.tell() - n * 20 - 4000))
        lines = f.read().decode().splitlines()
    i = max(k for k, l in enumerate(lines) if l.startswith("Layer 0"))
    vals = [float(l.split()[1]) for l in lines[i + 1:i + 1 + rows * rows]]
    return np.array(vals).reshape(rows, rows)


def main():
    fps = [f for f in tagen.generated(13) if f.name in PICK]
    cals = C.run_calibration_runs_many(fps)
    steady = datasets.steady_test_many(fps, n=300)
    traces = datasets.traces_many([(fp, "phase", 2000, "short") for fp in fps], dt=DT)

    fig, axes = plt.subplots(4, 4, figsize=(13, 11), layout="constrained")
    fig2, axes2 = plt.subplots(1, 4, figsize=(14, 3.3), sharey=True)
    rows = []
    for r, (fp, tr) in enumerate(zip(fps, traces)):
        cal, core = cals[fp.name], fp.power_idx
        t, Y = C.merged_samples(cal)
        s1, t3 = SteadyG(cal["G"], AMB), SumExp.calibrate(cal["G"], t, Y, 4, AMB)
        P, Tcached = steady[fp.name]["P"][VEC], steady[fp.name]["T"][VEC]
        res = H.steady(fp, P, group="extended_maps", model="grid", rows=64, grid_map=True, keep=False)
        assert np.abs(res["T"] - Tcached).max() < 1e-4, "cached truth differs from the re-run"
        grid, truth, pred = res["grid"] - 273.15, res["T"] - 273.15, s1.steady(P) - 273.15
        lo, hi = min(grid.min(), pred.min()), max(grid.max(), pred.max())
        W, Hd = fp.die
        ax = axes[r]
        im = ax[0].imshow(grid, extent=[0, W * 1e3, 0, Hd * 1e3], cmap="inferno", vmin=lo, vmax=hi)
        paint(ax[1], fp, truth, lo, hi); paint(ax[2], fp, pred, lo, hi)
        err = (pred - truth) * 1e6                                        # micro-kelvin
        m = max(np.abs(err).max(), 1e-9)
        ax[3].imshow(np.zeros((1, 1)), extent=[0, 1, 0, 1], cmap="coolwarm", vmin=-1, vmax=1, alpha=0)
        e_im = paint(ax[3], fp, err, -m, m, cmap="coolwarm")
        for a, ttl in zip(ax, ("HotSpot grid 64x64", "HotSpot, block average", "S1 prediction",
                               "S1 minus HotSpot (µK)")):
            a.set_title(ttl, fontsize=9)
            a.grid(False); a.set_xlabel("mm")
        ax[0].set_ylabel(f"{fp.name}\nmm", fontsize=9)
        fig.colorbar(im, ax=ax[:3], shrink=0.75, pad=0.01, label="°C")
        fig.colorbar(e_im, ax=ax[3], shrink=0.75, label="µK")
        rows.append(dict(floorplan=fp.name, total_power_W=float(P.sum()),
                         hotspot_peak_cell_C=float(grid.max()), hotspot_core_max_C=float(truth[core].max()),
                         s1_core_max_C=float(pred[core].max()),
                         s1_max_abs_err_uK=float(np.abs(err).max()),
                         grid_cell_minus_block_avg_max_K=float(grid.max() - truth[core].max())))
        # transient: T3 against HotSpot, 2 s phase trace from cold
        T3p = t3.transient(tr["P"], DT)[:, core]
        Tt = tr["T"][:, core]
        a = axes2[r]; tt = np.arange(len(Tt)) * DT
        k = int(np.argmax(Tt[-1]))
        a.plot(tt, Tt[:, k] - 273.15, "k", lw=1.6, label="HotSpot")
        a.plot(tt, T3p[:, k] - 273.15, "C3", lw=1.0, ls="--", label="T3 M=4")
        a.set(title=f"{fp.name} (hottest core)", xlabel="time (s)")
        rows[-1].update(t3_mae_K=float(np.abs(T3p - Tt).mean()), t3_max_K=float(np.abs(T3p - Tt).max()))
    # T3 heatmaps at t = 2 s (HotSpot's grid map at the last step of the trace)
    fig3, axes3 = plt.subplots(4, 4, figsize=(13, 11), layout="constrained")
    for r, (fp, tr) in enumerate(zip(fps, traces)):
        cal = cals[fp.name]
        t, Y = C.merged_samples(cal)
        t3 = SumExp.calibrate(cal["G"], t, Y, 4, AMB)
        res = H.transient(fp, tr["P"], DT, group="extended_maps", model="grid", rows=64, keep=True,
                          extra={"grid_transient_file": "out.grid.ttrace"})
        assert np.abs(res["T"] - tr["T"]).max() < 1e-4
        grid = last_grid(Path(res["dir"]) / "out.grid.ttrace") - 273.15
        H._cleanup(res["dir"])
        truth, pred = tr["T"][-1] - 273.15, t3.transient(tr["P"], DT)[-1] - 273.15
        lo, hi = min(grid.min(), pred.min()), max(grid.max(), pred.max())
        W, Hd = fp.die
        ax = axes3[r]
        im = ax[0].imshow(grid, extent=[0, W * 1e3, 0, Hd * 1e3], cmap="inferno", vmin=lo, vmax=hi)
        paint(ax[1], fp, truth, lo, hi); paint(ax[2], fp, pred, lo, hi)
        err = pred - truth
        m = max(np.abs(err).max(), 1e-9)
        e_im = paint(ax[3], fp, err, -m, m, cmap="coolwarm")
        for a, ttl in zip(ax, ("HotSpot grid 64x64, t = 2 s", "HotSpot, block average",
                               "T3 (M = 4) prediction", "T3 minus HotSpot (K)")):
            a.set_title(ttl, fontsize=9); a.grid(False); a.set_xlabel("mm")
        ax[0].set_ylabel(f"{fp.name}\nmm", fontsize=9)
        fig3.colorbar(im, ax=ax[:3], shrink=0.75, pad=0.01, label="°C")
        fig3.colorbar(e_im, ax=ax[3], shrink=0.75, label="K")
        rows[r].update(t3_end_max_abs_err_K=float(np.abs(err).max()),
                       t3_end_core_max_C=float(pred[fp.power_idx].max()),
                       hotspot_end_core_max_C=float(truth[fp.power_idx].max()),
                       hotspot_end_peak_cell_C=float(grid.max()))
    fig3.savefig(OUT / "heatmaps_t3.png")
    axes2[0].set_ylabel("°C"); axes2[0].legend(fontsize=8)
    fig.savefig(OUT / "heatmaps.png"); fig2.savefig(OUT / "transient_check.png")
    save_csv(OUT / "heatmaps_summary.csv", rows)
    for x in rows:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in x.items()})


if __name__ == "__main__":
    main()
