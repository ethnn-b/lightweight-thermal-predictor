"""P0-3: block model vs grid model, grid resolution, and hot spots inside cores.

On the main subset at TA nominal power:
  (a) block model vs grid 64x64, per core;
  (b) grid 32 / 64 / 128: is 64x64 (the TA's choice) fine enough?
  (c) hottest grid cell inside each core vs the core's average (what DTM would miss);
  (d) HotSpot runtime of one steady run for each model (median of 5).
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, gridmap as GM
from src.sim.parallel import pmap

OUT = results_dir(__file__)
G = "P0-3"
SETTINGS = [("block", 64), ("grid", 32), ("grid", 64), ("grid", 128)]


def run(fp_name, model, rows):
    fp = F.get(fp_name)
    return H.steady(fp, fp.nominal_power(), group=G, model=model, rows=rows,
                    grid_map=(model == "grid"), keep=False)


def main():
    jobs = [dict(fp_name=n, model=m, rows=r) for n in F.MAIN_SUBSET for m, r in SETTINGS]
    res = dict(zip([(j["fp_name"], j["model"], j["rows"]) for j in jobs], pmap(run, jobs)))

    # timing: 5 sequential repeats each, on one floorplan, nothing else running
    timing = []
    for m, r in SETTINGS:
        walls = [run(F.MAIN_SUBSET[0], m, r)["wall_s"] for _ in range(5)]
        timing.append(dict(model=f"{m} {r}x{r}" if m == "grid" else "block",
                           median_wall_s=float(np.median(walls))))

    rows, per_core = [], []
    for n in F.MAIN_SUBSET:
        fp = F.get(n)
        core = fp.power_idx
        Tb = res[(n, "block", 64)]["T"]
        T32, T64, T128 = (res[(n, "grid", r)]["T"] for r in (32, 64, 128))
        hot, area_avg = {}, {}
        for r in (32, 64, 128):
            g = res[(n, "grid", r)]["grid"].ravel()
            cells = GM.block_cells(fp, r, r)
            hot[r] = np.array([g[cells[i]].max() for i in range(len(fp.blocks))])
            # exact area-weighted average: separates real resolution effects from HotSpot's
            # habit of counting partial boundary cells with full weight
            area_avg[r] = GM.overlap_weights(fp, r, r) @ g
        for i in core:
            per_core.append(dict(floorplan=n, core=fp.names[i], type=fp.types[i],
                                 block_C=Tb[i] - 273.15, grid32_C=T32[i] - 273.15,
                                 grid64_C=T64[i] - 273.15, grid128_C=T128[i] - 273.15,
                                 hottest_cell64_C=hot[64][i] - 273.15,
                                 hottest_cell128_C=hot[128][i] - 273.15))
        rows.append(dict(
            floorplan=n,
            block_vs_grid64_maxdiff_K=float(np.abs(Tb[core] - T64[core]).max()),
            grid32_vs_128_maxdiff_K=float(np.abs(T32[core] - T128[core]).max()),
            grid64_vs_128_maxdiff_K=float(np.abs(T64[core] - T128[core]).max()),
            areaavg32_vs_128_maxdiff_K=float(np.abs(area_avg[32] - area_avg[128])[core].max()),
            areaavg64_vs_128_maxdiff_K=float(np.abs(area_avg[64] - area_avg[128])[core].max()),
            hotspot_avg_vs_area_avg64_max_K=float(np.abs(T64 - area_avg[64])[core].max()),
            hotcell_minus_avg64_max_K=float((hot[64] - T64)[core].max()),
            hotcell_minus_avg128_max_K=float((hot[128] - T128)[core].max()),
            peak_grid64_C=float(T64[core].max() - 273.15),
            peak_cell128_C=float(hot[128][core].max() - 273.15),
        ))

    save_csv(OUT / "summary.csv", rows)
    save_csv(OUT / "per_core.csv", per_core)
    save_csv(OUT / "timing.csv", timing)
    print(md_table(rows, "{:.3g}")); print(); print(md_table(timing, "{:.3g}"))
    save_json(OUT / "summary.json", dict(rows=rows, timing=timing))

    # figure 1: per-core temperatures, block vs grid vs hottest cell, for each floorplan
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.2), sharey=True)
    for ax, n in zip(axes, F.MAIN_SUBSET):
        pc = [r for r in per_core if r["floorplan"] == n]
        x = np.arange(len(pc))
        for k, (key, lab) in enumerate([("block_C", "block model"), ("grid64_C", "grid 64 avg"),
                                        ("grid128_C", "grid 128 avg"),
                                        ("hottest_cell128_C", "hottest cell (128)")]):
            ax.bar(x + (k - 1.5) * 0.2, [r[key] for r in pc], 0.2, label=lab)
        ax.set_xticks(x, [f"{r['core'].split('_')[1]}\n{r['type'][0].upper()}" for r in pc])
        ax.set_title(n); ax.set_ylim(55, None)
    axes[0].set_ylabel("temperature (°C)"); axes[0].legend(fontsize=7)
    fig.savefig(OUT / "per_core.png")

    # figure 2: 128x128 maps with block outlines
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.4))
    for ax, n in zip(axes, F.MAIN_SUBSET):
        fp = F.get(n)
        W, Hd = fp.die
        g = res[(n, "grid", 128)]["grid"] - 273.15
        im = ax.imshow(g, extent=[0, W * 1e3, 0, Hd * 1e3], cmap="inferno")
        for b, t in zip(fp.blocks, fp.types):
            ax.add_patch(plt.Rectangle((b.x * 1e3, b.y * 1e3), b.w * 1e3, b.h * 1e3, fill=False,
                                       ec="w" if t != "fill" else "grey", lw=0.8,
                                       ls="-" if t != "fill" else ":"))
        ax.set_title(n); ax.set_xlabel("mm"); ax.grid(False)
        fig.colorbar(im, ax=ax, shrink=0.8, label="°C")
    fig.savefig(OUT / "maps_128.png")


if __name__ == "__main__":
    main()
