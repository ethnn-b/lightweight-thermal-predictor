"""Stage 3 report figure: T3 at the end of the 2 s test trace, one generated floorplan per style.

Same data as maps.py (cached calibration runs and 2 s phase traces), without HotSpot's 64x64
grid column: HotSpot's block averages, T3's prediction and T3 minus HotSpot, per floorplan.

    PYTHONPATH=. python3 experiments/extended_validation/maps_report.py
"""
import numpy as np

from common import results_dir, plt
from src.sim import hotspot as H, datasets, tagen
from src.ltp import calibrate as C
from src.ltp.models import SumExp
from maps import paint, PICK, AMB, DT

OUT = results_dir(__file__)


def main():
    fps = [f for f in tagen.generated(13) if f.name in PICK]
    cals = C.run_calibration_runs_many(fps)
    traces = datasets.traces_many([(fp, "phase", 2000, "short") for fp in fps], dt=DT)
    fig, axes = plt.subplots(4, 3, figsize=(9.5, 11), layout="constrained")
    for r, (fp, tr) in enumerate(zip(fps, traces)):
        cal = cals[fp.name]
        t, Y = C.merged_samples(cal)
        t3 = SumExp.calibrate(cal["G"], t, Y, 4, AMB)
        truth, pred = tr["T"][-1] - 273.15, t3.transient(tr["P"], DT)[-1] - 273.15
        lo, hi = min(truth.min(), pred.min()), max(truth.max(), pred.max())
        ax = axes[r]
        im = paint(ax[0], fp, truth, lo, hi)
        paint(ax[1], fp, pred, lo, hi)
        err = pred - truth
        m = max(np.abs(err).max(), 1e-9)
        e_im = paint(ax[2], fp, err, -m, m, cmap="coolwarm")
        for a, ttl in zip(ax, ("HotSpot, t = 2 s", "T3 (M = 4) prediction", "T3 minus HotSpot (K)")):
            a.set_title(ttl, fontsize=10); a.grid(False); a.set_xlabel("mm")
        ax[0].set_ylabel(f"{fp.name}\nmm", fontsize=10)
        fig.colorbar(im, ax=ax[:2], shrink=0.8, pad=0.01, label="°C")
        fig.colorbar(e_im, ax=ax[2], shrink=0.8, label="K")
        print(fp.name, "max |T3 - HotSpot| at t = 2 s:", round(float(m), 4), "K")
    fig.savefig(OUT / "heatmaps_t3_report.png", dpi=150)


if __name__ == "__main__":
    main()
