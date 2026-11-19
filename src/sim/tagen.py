"""tagen.py: generate more floorplans in the TA styles (plan.md P0-5(d), dataset.md §1.9).

Same cores as the TA set (2 big 4x4 mm + 6 little 2x2 mm), same file format and layer stack
(.flp + _tim.flp + .lcf), whole-millimetre coordinates, white space tiled with FILL blocks.
The rules imitate each style; they are not the TA's own generator:
  Style_1  big cores side by side, little cores in a 3x2 cluster, the two groups apart
  Style_2  dense: cores packed with no gaps on a small die (60-95 % cores)
  Style_3  elongated or larger die, at least 1 mm between cores
  Style_4  14x14 mm die, cores scattered, at least 1 mm between cores
Output: data/generated/Style_k/gen_XXX/ with the TA file names.
"""
from pathlib import Path

import numpy as np

from .floorplans import REPO, SILICON, TIM, Floorplan

GEN_DIR = REPO / "data" / "generated"
BIG, LITTLE = 4, 2
DIES = {1: [(9, 10), (9, 11), (16, 8), (10, 10), (11, 9)],
        2: [(10, 8), (9, 10), (12, 6), (10, 6), (8, 8), (12, 7)],
        3: [(7, 14), (13, 12), (14, 6), (6, 14), (12, 10), (8, 13)],
        4: [(14, 14)]}


def _free(occ, x, y, w, h, gap):
    H, W = occ.shape
    if x < 0 or y < 0 or x + w > W or y + h > H:
        return False
    x0, y0, x1, y1 = max(0, x - gap), max(0, y - gap), min(W, x + w + gap), min(H, y + h + gap)
    return not occ[y0:y1, x0:x1].any()


def _place(occ, w, h, gap, rng, tries=400):
    H, W = occ.shape
    for _ in range(tries):
        x, y = rng.integers(0, W - w + 1), rng.integers(0, H - h + 1)
        if _free(occ, x, y, w, h, gap):
            occ[y:y + h, x:x + w] = True
            return x, y
    return None


def _layout(style, rng):
    W, H = DIES[style][rng.integers(len(DIES[style]))]
    occ = np.zeros((H, W), bool)
    cores = []
    if style == 1:
        # bigs side by side, little 3x2 cluster, the groups at least 1 mm apart
        for _ in range(200):
            occ[:] = False
            pb = _place(occ, 2 * BIG, BIG, 0, rng)
            if pb is None:
                continue
            horiz = rng.random() < 0.5
            cw, ch = (3 * LITTLE, 2 * LITTLE) if horiz else (2 * LITTLE, 3 * LITTLE)
            pl = _place(occ, cw, ch, 1, rng)
            if pl is None:
                continue
            cores = [("big", pb[0], pb[1]), ("big", pb[0] + BIG, pb[1])]
            cols = 3 if horiz else 2
            cores += [("little", pl[0] + LITTLE * (k % cols), pl[1] + LITTLE * (k // cols))
                      for k in range(6)]
            return W, H, cores
        return None
    gap = {2: 0, 3: 1, 4: 1}[style]
    for _ in range(200):
        occ[:] = False
        cores = []
        for t, s in [("big", BIG)] * 2 + [("little", LITTLE)] * 6:
            p = _place(occ, s, s, gap, rng)
            if p is None:
                break
            cores.append((t, p[0], p[1]))
        if len(cores) == 8:
            return W, H, cores
    return None


def _fill_rects(occ):
    """Tile the free cells with rectangles: greedy, row-major, widest run then extend down."""
    H, W = occ.shape
    used = occ.copy()
    rects = []
    for y in range(H):
        x = 0
        while x < W:
            if used[y, x]:
                x += 1
                continue
            w = 1
            while x + w < W and not used[y, x + w]:
                w += 1
            h = 1
            while y + h < H and not used[y + h, x:x + w].any():
                h += 1
            used[y:y + h, x:x + w] = True
            rects.append((x, y, w, h))
            x += w
    return rects


def generate(style, n, seed=0):
    """Write n floorplans of a style; returns their Floorplan objects."""
    rng = np.random.default_rng(1000 * style + seed)
    out = []
    k = 0
    while len(out) < n:
        lay = _layout(style, rng)
        if lay is None:
            continue
        k += 1
        name = f"gen_{k:03d}"
        write_floorplan(GEN_DIR / f"Style_{style}" / name, name, *lay)
        out.append(load(style, name))
    return out


def write_floorplan(d, name, W, H, cores):
    """Write one layout (die W x H mm, cores from _layout) as TA-style files in folder d."""
    occ = np.zeros((H, W), bool)
    for t, x, y in cores:
        s = BIG if t == "big" else LITTLE
        occ[y:y + s, x:x + s] = True
    # y in the occupancy grid counts from the bottom; HotSpot uses bottom-left coordinates
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, (t, x, y) in enumerate(sorted(cores, key=lambda c: c[0] != "big")):
        s = BIG if t == "big" else LITTLE
        lines.append(f"Core_{i}_L0 {s/1e3:.6f} {s/1e3:.6f} {x/1e3:.6f} {y/1e3:.6f}")
    for i, (x, y, w, h) in enumerate(_fill_rects(occ)):
        lines.append(f"FILL_{i}_L0 {w/1e3:.6f} {h/1e3:.6f} {x/1e3:.6f} {y/1e3:.6f}")
    (d / f"{name}_layer_0.flp").write_text("\n".join(lines) + "\n")
    (d / f"{name}_tim.flp").write_text(f"TIM_Top {W/1e3:.6f} {H/1e3:.6f} 0.000000 0.000000\n")
    (d / f"{name}.lcf").write_text(
        "# Layer 0: Silicon\n0\nY\nY\n"
        f"{SILICON['cap']:g}\n{SILICON['res']:g}\n{SILICON['thick']:g}\n{name}_layer_0.flp\n\n"
        "# Layer 1: TIM\n1\nY\nN\n"
        f"{TIM['cap']:g}\n{TIM['res']:g}\n{TIM['thick']:g}\n{name}_tim.flp\n")


def load(style, name):
    d = GEN_DIR / f"Style_{style}" / name
    return Floorplan(name=f"g{style}_{name.replace('gen_', 'gen')}", dir=d,
                     flp=d / f"{name}_layer_0.flp", lcf=d / f"{name}.lcf",
                     extra_files=[d / f"{name}_tim.flp"], style=f"gen_Style_{style}")


def generated(per_style=10):
    """The generated set (created on first use): per_style floorplans for each style."""
    out = []
    for s in (1, 2, 3, 4):
        names = sorted(p.name for p in (GEN_DIR / f"Style_{s}").glob("gen_*")) \
            if (GEN_DIR / f"Style_{s}").exists() else []
        if len(names) >= per_style:
            out += [load(s, n) for n in names[:per_style]]
        else:
            out += generate(s, per_style)
    return out
