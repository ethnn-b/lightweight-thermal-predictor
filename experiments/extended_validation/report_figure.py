"""Figure for the Stage 4 report: two steady results and two transient results.

Crops the rows of g1_gen012 and g3_gen012 from heatmaps.png (steady, S1) and heatmaps_t3.png
(transient at t = 2 s, T3 M = 4), both written by maps.py, and stacks them into one image.

    python3 experiments/extended_validation/report_figure.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).parent / "results"
ROWS = {"g1_gen012": (0, 378), "g3_gen012": (639, 968)}   # pixel rows in the 4 x 4 grids


def main():
    parts = []
    for src in ("heatmaps.png", "heatmaps_t3.png"):
        img = np.asarray(Image.open(OUT / src).convert("RGB"))
        parts += [img[a:b] for a, b in ROWS.values()]
    Image.fromarray(np.vstack(parts)).save(OUT / "report_steady_transient.png")


if __name__ == "__main__":
    main()
