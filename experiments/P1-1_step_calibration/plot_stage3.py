"""P1-1 figure for the Stage 3 report (v4 on): step responses of one floorplan with T1 and
T3 (M = 2 and M = 4), self-heating only (no coupling curves). HotSpot is drawn as one curve: the
1 ms run up to 2 s and the 20 ms run after it.

Reads the cached calibration runs ($LTP_RUNS/calib/s4_fp001.npz); no new HotSpot runs.
Run inside WSL, like the experiments:

    PYTHONPATH="$PWD:$PWD/experiments" python3 experiments/P1-1_step_calibration/plot_stage3.py
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import plt  # noqa: E402
from src.sim import floorplans as F, hotspot as H  # noqa: E402
from src.ltp import calibrate as C  # noqa: E402
from src.ltp.models import FirstOrderLag, SumExp  # noqa: E402

OUT = HERE / "results"


def main():
    n = "s4_fp001"
    fp = F.get(n)
    cal = C.run_calibration_runs_many([fp])[n]          # cached
    G = cal["G"]
    t, Y = C.merged_samples(cal)
    t1 = FirstOrderLag.calibrate(G, t, [Y[:, :, j] for j in range(fp.n_power)], H.AMBIENT)
    t3 = {M: SumExp.calibrate(G, t, Y, M, H.AMBIENT) for M in (2, 4)}
    tt = np.logspace(-3, 2, 300)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, j in zip(axes, [0, 2]):
        i = fp.power_idx[j]
        # HotSpot as one curve, combined the way calibration uses it: the 1 ms run up to
        # T_SWITCH (2 s), the 20 ms run after it
        fine = cal["t_fine"] <= C.T_SWITCH
        coarse = cal["t_coarse"] > C.T_SWITCH
        ax.semilogx(np.concatenate([cal["t_fine"][fine], cal["t_coarse"][coarse]]),
                    np.concatenate([cal["Y_fine"][fine, i, j], cal["Y_coarse"][coarse, i, j]]),
                    "k", lw=2, label="HotSpot")
        ax.semilogx(tt, t3[4].step_response(tt)[:, i, j], "C1--", label="T3 (M = 4)")
        ax.semilogx(tt, t3[2].step_response(tt)[:, i, j], "C2-.", label="T3 (M = 2)")
        ax.semilogx(tt, G[i, j] * (1 - np.exp(-tt / t1.tau[i])), "C0:", label="T1")
        ax.set(xlabel="time after a 1 W step (s)", ylabel="temperature rise (K)")
        ax.set_title(f"{n}: 1 W in {fp.power_names[j]} ({fp.power_types[j]})", fontsize=9)
        ax.legend(fontsize=7)
    fig.savefig(OUT / "step_response_fits_stage3.png")


if __name__ == "__main__":
    main()
