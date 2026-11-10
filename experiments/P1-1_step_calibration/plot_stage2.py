"""P1-1 figure for the Stage 2 report: calibrated G of the four main floorplans, as a readable 2x2
grid (the 1x4 G_heatmaps.png is too cramped at page width).

Reads results/models/<fp>_S1.npz (no HotSpot runs).

    python experiments/P1-1_step_calibration/plot_stage2.py
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import plt  # noqa: E402
from src.sim import floorplans as F  # noqa: E402

OUT = HERE / "results"


def main():
    plt.rcParams.update({"font.size": 11})
    fig, axes = plt.subplots(2, 2, figsize=(10, 9), constrained_layout=True)
    for ax, n in zip(axes.flat, F.MAIN_SUBSET):
        fp = F.get(n)
        d = np.load(OUT / "models" / f"{n}_S1.npz", allow_pickle=True)
        Gc = d["G"][fp.power_idx]
        im = ax.imshow(Gc, cmap="viridis", vmin=0)
        lab = [f"{x.split('_')[1]}{t[0].upper()}" for x, t in zip(fp.power_names, fp.power_types)]
        ax.set_xticks(range(len(lab)), lab)
        ax.set_yticks(range(len(lab)), lab)
        ax.set(title=n, xlabel="heated core j", ylabel="core i")
        ax.grid(False)
        fig.colorbar(im, ax=ax, shrink=0.85, label="$G_{ij}$ (K/W)")
    fig.savefig(OUT / "G_heatmaps_stage2.png", dpi=200)


if __name__ == "__main__":
    main()
