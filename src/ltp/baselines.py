"""baselines.py: predictors that need no calibration runs on the target floorplan.

S0 power blurring: one generic radial heat-spread kernel K(r) (K/W), measured once with a single
point-source HotSpot run on a large reference die, then convolved with any floorplan's power map.
It is not floorplan-specific, so it cannot know about die edges or the package geometry of the
target; that is exactly what calibration adds (P1-3).
"""
import numpy as np

from src.sim import floorplans as F, hotspot as H, gridmap as GM

KERNEL_CACHE = H.RUNS / "calib" / "s0_kernel.npz"


def s0_kernel(refresh=False):
    """(r_mm, K_per_W): a 0.44 mm square 1 W source at the centre of a 28x28 mm die (TA stack,
    grid 128x128), radially averaged."""
    if KERNEL_CACHE.exists() and not refresh:
        d = np.load(KERNEL_CACHE)
        return d["r_mm"], d["K_per_W"]
    d = F.REPO / "floorplans" / "stacks" / "s0_kernel"
    d.mkdir(parents=True, exist_ok=True)
    L, s = 28.0, 28.0 / 64        # mm; source = 2x2 cells of the 128 grid
    c0, c1 = (L - s) / 2, (L + s) / 2
    rects = [("SRC", s, s, c0, c0), ("FILL_0", L, c0, 0, 0), ("FILL_1", L, L - c1, 0, c1),
             ("FILL_2", c0, s, 0, c0), ("FILL_3", L - c1, s, c1, c0)]
    flp = d / "s0_src.flp"
    flp.write_text("".join(f"{n}\t{w/1e3:.6f}\t{h/1e3:.6f}\t{x/1e3:.6f}\t{y/1e3:.6f}\n"
                           for n, w, h, x, y in rects))
    f, lcf, tim = F.write_ta_style_lcf(flp, d, "s0_kernel")
    fp = F.Floorplan(name="s0_kernel", dir=d, flp=f, lcf=lcf, extra_files=[tim], style="ref")
    r = H.steady(fp, [1.0], group="calib/s0_kernel", rows=128, grid_map=True)
    X, Y = GM.cell_centres(fp, 128, 128)
    rr = np.hypot(X * 1e3 - L / 2, Y * 1e3 - L / 2)
    rise = r["grid"].ravel() - H.AMBIENT
    k = np.digitize(rr, np.arange(0, rr.max() + 0.2, 0.2))
    rb = np.array([rr[k == i].mean() for i in np.unique(k)])
    kb = np.array([rise[k == i].mean() for i in np.unique(k)])
    KERNEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(KERNEL_CACHE, r_mm=rb, K_per_W=kb)
    return rb, kb


def G_s0(fp, kernel=None, rows=64):
    """Influence matrix predicted by power blurring: (n_blocks, N)."""
    rb, kb = s0_kernel() if kernel is None else kernel
    X, Y = GM.cell_centres(fp, rows, rows)
    X, Y = X * 1e3, Y * 1e3
    Wb = GM.overlap_weights(fp, rows, rows)          # block -> cell power split
    Hb = GM.hotspot_weights(fp, rows, rows)          # cell -> block temperature (HotSpot avg)
    G = np.zeros((len(fp.blocks), fp.n_power))
    for j, b in enumerate(fp.power_idx):
        rise = np.zeros(len(X))
        for s in np.nonzero(Wb[b])[0]:
            rise += Wb[b, s] * np.interp(np.hypot(X - X[s], Y - Y[s]), rb, kb)
        G[:, j] = Hb @ rise
    return G
