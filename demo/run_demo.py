"""Live demo: a brand-new floorplan and brand-new power, HotSpot against S1 and T3 (M = 4).

    1. generate a new floorplan in one of the TA styles (random seed unless --seed is given)
    2. generate a new steady power vector and a new transient power trace (phase trace, 1 ms)
    3. run HotSpot on both: the 64x64 steady map, and the 64x64 map at the end of the transient
    4. calibrate the predictor on the new floorplan (24 HotSpot runs), then predict with
       S1 (steady) and T3, M = 4 (transient)
    5. save the maps, plots, power files and a summary in demo/output/<floorplan>/

Run inside WSL from the repo root:  bash demo/run_demo.sh [--style 1-4] [--seed N] [--steps N]
"""
import argparse
import csv
import subprocess
import time
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.sim import hotspot as H, powergen, tagen  # noqa: E402
from src.sim.floorplans import Floorplan  # noqa: E402
from src.ltp import bench, calibrate as C  # noqa: E402
from src.ltp.models import SumExp  # noqa: E402
from src.ltp.predictor import Predictor  # noqa: E402

DEMO = Path(__file__).resolve().parent
AMB, DT, ROWS = H.AMBIENT, 1e-3, 64
K2C = 273.15
STYLE_TEXT = {1: "big cores side by side, little cores clustered",
              2: "dense: cores packed on a small die",
              3: "elongated or larger die, 1 mm between cores",
              4: "14 x 14 mm die, cores scattered"}
plt.rcParams.update({"figure.dpi": 130, "savefig.bbox": "tight", "font.size": 9})


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- 1. floorplan
def new_floorplan(style, seed, out):
    rng = np.random.default_rng(seed)
    lay = None
    while lay is None:
        lay = tagen._layout(style, rng)
    name = f"demo_s{style}_{seed}"
    d = out / "floorplan"
    tagen.write_floorplan(d, name, *lay)
    return Floorplan(name=name, dir=d, flp=d / f"{name}_layer_0.flp", lcf=d / f"{name}.lcf",
                     extra_files=[d / f"{name}_tim.flp"], style=f"demo_Style_{style}")


# ---------------------------------------------------------------- plotting helpers
def label(fp, i):
    """'C3 (L)' for Core_3_L0, a little core."""
    return f"C{fp.names[i].split('_')[1]} ({fp.types[i][0].upper()})"


def outline(ax, fp, color="white", text=True):
    for i in fp.power_idx:
        b = fp.blocks[i]
        ax.add_patch(plt.Rectangle((b.x * 1e3, b.y * 1e3), b.w * 1e3, b.h * 1e3,
                                   fc="none", ec=color, lw=0.8))
        if text:
            ax.text((b.x + b.w / 2) * 1e3, (b.y + b.h / 2) * 1e3, label(fp, i), color=color,
                    ha="center", va="center", fontsize=6.5)


def grid_image(ax, fp, grid, vmin, vmax, cmap="inferno"):
    W, Hd = fp.die
    im = ax.imshow(grid, extent=[0, W * 1e3, 0, Hd * 1e3], cmap=cmap, vmin=vmin, vmax=vmax)
    outline(ax, fp)
    return im


def block_image(ax, fp, T, vmin, vmax, cmap="inferno"):
    """Each block painted with one temperature (what a block-level predictor outputs)."""
    W, Hd = fp.die
    norm, cm = plt.Normalize(vmin, vmax), plt.get_cmap(cmap)
    for b, t in zip(fp.blocks, T):
        ax.add_patch(plt.Rectangle((b.x * 1e3, b.y * 1e3), b.w * 1e3, b.h * 1e3,
                                   fc=cm(norm(t)), ec="none"))
    ax.set_xlim(0, W * 1e3); ax.set_ylim(0, Hd * 1e3); ax.set_aspect("equal")
    outline(ax, fp, color="white" if cmap == "inferno" else "black")
    return plt.cm.ScalarMappable(norm, cm)


def last_grid(path, rows=ROWS):
    """Die layer (layer 0) at the last sample of a -grid_transient_file, read from the end of
    the file (HotSpot writes all 4 layers at every step, ~0.26 MB per step at 64 x 64)."""
    n = 4 * (rows * rows + 1)
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - n * 20 - 4000))
        lines = f.read().decode().splitlines()
    i = max(k for k, l in enumerate(lines) if l.startswith("Layer 0"))
    return np.array([float(l.split()[1]) for l in lines[i + 1:i + 1 + rows * rows]]).reshape(rows, rows)


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--style", type=int, choices=[1, 2, 3, 4], default=None,
                    help="TA style of the new floorplan (default: random)")
    ap.add_argument("--seed", type=int, default=None, help="seed for floorplan and power (default: new)")
    ap.add_argument("--steps", type=int, default=2000, help="transient length in 1 ms steps (default 2000)")
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    rng = np.random.default_rng(seed)
    style = a.style or int(rng.integers(1, 5))

    # 1. floorplan ---------------------------------------------------------------
    fp_name = f"demo_s{style}_{seed}"
    out = DEMO / "output" / fp_name
    out.mkdir(parents=True, exist_ok=True)
    fp = new_floorplan(style, seed, out)
    core = fp.power_idx
    W, Hd = fp.die
    log(f"[1] new floorplan {fp.name}: Style_{style} ({STYLE_TEXT[style]}), die "
        f"{W * 1e3:g} x {Hd * 1e3:g} mm, {fp.n_power} cores + {len(fp.names) - fp.n_power} FILL blocks")
    log(f"    files: {fp.dir}")

    # 2. power -------------------------------------------------------------------
    p = powergen.random_steady(fp, 1, seed=seed + 1)[0]
    P = powergen.phase_trace(fp, a.steps, seed=seed + 2, max_phase=a.steps // 2)
    H.write_ptrace(out / "steady_power.ptrace", fp.names, fp.full_power(p))
    H.write_ptrace(out / "transient_power.ptrace", fp.names, np.array([fp.full_power(r) for r in P]))
    log(f"[2] new power: steady {p.sum():.1f} W total ({', '.join(f'{x:.1f}' for x in p)} W); "
        f"transient {a.steps} steps of 1 ms, {P.sum(1).min():.0f}-{P.sum(1).max():.0f} W")

    # 3. HotSpot -----------------------------------------------------------------
    log("[3] HotSpot (64 x 64 grid model)...")
    hs = H.steady(fp, p, group=f"demo/{fp.name}", grid_map=True, keep=False)
    hs_grid, hs_T = hs["grid"], hs["T"]
    log(f"    steady:    {hs['wall_s']:.2f} s")
    tr = H.transient(fp, P, DT, group=f"demo/{fp.name}", keep=True,
                     extra={"grid_transient_file": "out.grid.ttrace"})
    hs_grid_end, hs_Tt = last_grid(Path(tr["dir"]) / "out.grid.ttrace"), tr["T"]
    H._cleanup(tr["dir"])
    # the map's block averages must equal HotSpot's own block temperatures at the last step
    from src.sim.gridmap import hotspot_weights
    chk = np.abs(hotspot_weights(fp, ROWS, ROWS) @ hs_grid_end.ravel() - hs_Tt[-1]).max()
    assert chk < 1e-3, f"end-of-transient map does not match the last ttrace row ({chk} K)"
    log(f"    transient: {tr['wall_s']:.2f} s for {a.steps} steps (incl. writing a 64 x 64 map every step)")

    # 4. calibrate + predict -----------------------------------------------------
    log("[4] calibration: 24 HotSpot runs on the new floorplan (once per floorplan)...")
    t0 = time.perf_counter()
    cal = C.run_calibration_runs(fp)
    t_cal = time.perf_counter() - t0
    t, Y = C.merged_samples(cal)
    t3 = SumExp.calibrate(cal["G"], t, Y, 4, AMB)
    pred = Predictor(fp.names, fp.power_names, AMB, cal["G"], t3.A, t3.tau)
    pred.save(out / "model.npz", floorplan=fp.name)
    log(f"    done in {t_cal:.0f} s wall ({cal['hotspot_s_steady'].sum() + cal['hotspot_s_transient'].sum():.0f} "
        f"CPU-s of HotSpot); model {pred.size_bytes()} B -> model.npz; "
        f"T3 time constants {', '.join(f'{x:.3g}' for x in t3.tau)} s")

    s1_T, t3_Tt = pred.steady(p), pred.transient(P, DT)
    s1_t = bench.time_call(pred.steady, [(p,)])[0]                # median of 10,000 calls
    t3_t = bench.time_per_step(pred.transient, P, DT) * len(P)    # whole trace, median of 5
    e_s = s1_T[core] - hs_T[core]
    e_t = t3_Tt[-1, core] - hs_Tt[-1, core]
    e_all = t3_Tt[:, core] - hs_Tt[:, core]
    log(f"    S1 steady:    {s1_t * 1e6:.0f} us, max |error| {np.abs(e_s).max():.1e} K on the cores")
    log(f"    T3 transient: {t3_t * 1e3:.1f} ms for {a.steps} steps; at t = {a.steps * DT:g} s "
        f"max |error| {np.abs(e_t).max():.3f} K; over the whole trace mean {np.abs(e_all).mean():.3f} K, "
        f"max {np.abs(e_all).max():.3f} K")

    # 5. figures -----------------------------------------------------------------
    log("[5] saving figures...")
    asp = Hd / W
    names_c = [label(fp, i) for i in core]

    # floorplan + powers
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 4.2), layout="constrained",
                           gridspec_kw=dict(width_ratios=[1, 1.4]))
    block_image(ax[0], fp, [0.6 if i in core else 0.15 for i in range(len(fp.names))], 0, 1, "Greys")
    ax[0].set(title=f"{fp.name}: {W * 1e3:g} x {Hd * 1e3:g} mm, Style_{style}", xlabel="mm", ylabel="mm")
    tt = np.arange(1, a.steps + 1) * DT
    for j in range(fp.n_power):
        ax[1].plot(tt, P[:, j], lw=1, label=names_c[j])
    ax[1].set(title="transient power trace (new)", xlabel="time (s)", ylabel="W")
    ax[1].legend(fontsize=7, ncol=4)
    fig.savefig(out / "1_floorplan_and_power.png"); plt.close(fig)

    # steady maps
    lo = min(hs_grid.min(), s1_T.min()) - K2C
    hi = max(hs_grid.max(), s1_T.max()) - K2C
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.6 * asp + 1.3), layout="constrained")
    im = grid_image(ax[0], fp, hs_grid - K2C, lo, hi)
    block_image(ax[1], fp, hs_T - K2C, lo, hi)
    block_image(ax[2], fp, s1_T - K2C, lo, hi)
    d = (s1_T - hs_T) * 1e6
    m = max(np.abs(d).max(), 1e-9)
    e1 = block_image(ax[3], fp, d, -m, m, "coolwarm")
    for a_, ttl in zip(ax, ["HotSpot, 64 x 64 grid", "HotSpot, block averages",
                            "S1 prediction", "S1 minus HotSpot (µK)"]):
        a_.set_title(ttl); a_.set_xlabel("mm")
    fig.colorbar(im, ax=ax[:3], shrink=0.8, label="°C")
    fig.colorbar(e1, ax=ax[3], shrink=0.8, label="µK")
    fig.suptitle(f"Steady state, {fp.name}, new power vector ({p.sum():.1f} W). "
                 f"HotSpot {hs['wall_s']:.2f} s, S1 {s1_t * 1e6:.0f} µs")
    fig.savefig(out / "2_steady_maps.png"); plt.close(fig)

    # transient maps at the end
    lo = min(hs_grid_end.min(), t3_Tt[-1].min()) - K2C
    hi = max(hs_grid_end.max(), t3_Tt[-1].max()) - K2C
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.6 * asp + 1.3), layout="constrained")
    im = grid_image(ax[0], fp, hs_grid_end - K2C, lo, hi)
    block_image(ax[1], fp, hs_Tt[-1] - K2C, lo, hi)
    block_image(ax[2], fp, t3_Tt[-1] - K2C, lo, hi)
    d = t3_Tt[-1] - hs_Tt[-1]
    m = max(np.abs(d).max(), 1e-9)
    e1 = block_image(ax[3], fp, d, -m, m, "coolwarm")
    for a_, ttl in zip(ax, [f"HotSpot, 64 x 64 grid", "HotSpot, block averages",
                            "T3 (M = 4) prediction", "T3 minus HotSpot (K)"]):
        a_.set_title(ttl); a_.set_xlabel("mm")
    fig.colorbar(im, ax=ax[:3], shrink=0.8, label="°C")
    fig.colorbar(e1, ax=ax[3], shrink=0.8, label="K")
    fig.suptitle(f"Transient, end of the trace (t = {a.steps * DT:g} s, cold start), {fp.name}. "
                 f"HotSpot {tr['wall_s']:.1f} s, T3 {t3_t * 1e3:.1f} ms")
    fig.savefig(out / "3_transient_maps_end.png"); plt.close(fig)

    # transient core temperatures over time
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True, layout="constrained",
                           gridspec_kw=dict(height_ratios=[3, 1]))
    for j, i in enumerate(core):
        ax[0].plot(tt, hs_Tt[:, i] - K2C, color=f"C{j}", lw=1.4, label=names_c[j])
        ax[0].plot(tt, t3_Tt[:, i] - K2C, color="black", lw=0.7, ls="--")
    ax[0].plot([], [], color="black", lw=0.7, ls="--", label="T3 (dashed)")
    ax[0].set(ylabel="°C", title="Core temperatures: HotSpot (solid) and T3 (dashed)")
    ax[0].legend(fontsize=7, ncol=5)
    ax[1].plot(tt, np.abs(e_all).max(1), lw=0.8, color="C3")
    ax[1].set(xlabel="time (s)", ylabel="worst core |error| (K)")
    for a_ in ax:
        a_.grid(alpha=0.3)
    fig.savefig(out / "4_transient_over_time.png"); plt.close(fig)

    # tables
    write_csv(out / "cores.csv", [dict(core=names_c[j], steady_power_W=round(p[j], 3),
                                       steady_HotSpot_C=round(hs_T[i] - K2C, 6),
                                       steady_S1_C=round(s1_T[i] - K2C, 6),
                                       steady_error_K=f"{s1_T[i] - hs_T[i]:.2e}",
                                       end_power_W=round(P[-1, j], 3),
                                       end_HotSpot_C=round(hs_Tt[-1, i] - K2C, 4),
                                       end_T3_C=round(t3_Tt[-1, i] - K2C, 4),
                                       end_error_K=round(t3_Tt[-1, i] - hs_Tt[-1, i], 4))
                                  for j, i in enumerate(core)])
    np.savez_compressed(out / "maps.npz", hotspot_steady_grid=hs_grid,
                        hotspot_transient_end_grid=hs_grid_end, hotspot_T=hs_T, s1_T=s1_T,
                        hotspot_Tt=hs_Tt, t3_Tt=t3_Tt, names=fp.names)
    summary = f"""floorplan      {fp.name} (Style_{style}, die {W * 1e3:g} x {Hd * 1e3:g} mm, seed {seed})
steady power   {p.sum():.2f} W   transient: {a.steps} steps x 1 ms, cold start

                          HotSpot (64x64 grid)     predictor
steady                    {hs['wall_s']:8.3f} s               S1 {s1_t * 1e6:8.1f} us   max core error {np.abs(e_s).max():.1e} K
transient                 {tr['wall_s']:8.2f} s               T3 {t3_t * 1e3:8.2f} ms   end max error {np.abs(e_t).max():.3f} K, trace mean {np.abs(e_all).mean():.3f} K / max {np.abs(e_all).max():.3f} K
hottest core (steady)     {names_c[int(np.argmax(hs_T[core]))]:>10s} {hs_T[core].max() - K2C:.3f} C     {names_c[int(np.argmax(s1_T[core]))]} {s1_T[core].max() - K2C:.3f} C
hottest core (end)        {names_c[int(np.argmax(hs_Tt[-1, core]))]:>10s} {hs_Tt[-1, core].max() - K2C:.3f} C     {names_c[int(np.argmax(t3_Tt[-1, core]))]} {t3_Tt[-1, core].max() - K2C:.3f} C
calibration (once)        24 HotSpot runs, {t_cal:.0f} s wall; model {pred.size_bytes()} B
(the transient HotSpot time includes writing a 64x64 map at every step)
"""
    (out / "summary.txt").write_text(summary)
    log("\n" + summary)
    log(f"output folder: {out}")
    try:   # the same folder as Windows sees it, to paste into Explorer
        win = subprocess.run(["wslpath", "-w", str(out)], capture_output=True, text=True).stdout.strip()
        if win:
            log(f"Windows path:  {win}")
    except OSError:
        pass


if __name__ == "__main__":
    main()
