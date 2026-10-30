"""P0-5(d): more floorplans in the TA styles (src/sim/tagen.py).

The TA README calls its floorplans "templates for generating more data". We generate 10 per
style with the same cores, file format and layer stack, then check they behave like the TA ones:
peak temperature at TA nominal power per style, compared with the TA floorplans of that style.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, tagen
from src.sim.parallel import pmap

OUT = results_dir(__file__)


def nominal(fp):
    r = H.steady(fp, fp.nominal_power(), group="P0-5d", keep=False)
    return float(r["T"][fp.power_idx].max() - 273.15)


def main():
    gen = tagen.generated(10)
    ta = F.ta_floorplans()
    peaks = pmap(nominal, [dict(fp=fp) for fp in gen + ta])
    rows = []
    for fp, pk in zip(gen + ta, peaks):
        W, Hd = fp.die
        rows.append(dict(floorplan=fp.name, set="generated" if fp in gen else "TA",
                         style=fp.style.replace("gen_", ""), die_mm=f"{W*1e3:g}x{Hd*1e3:g}",
                         core_area_pct=100 * fp.power_areas_mm2.sum() / (W * Hd * 1e6),
                         fill_blocks=fp.types.count("fill"), nominal_peak_C=pk))
    save_csv(OUT / "floorplans.csv", rows)
    summ = []
    for st in ["Style_1", "Style_2", "Style_3", "Style_4"]:
        for s in ("TA", "generated"):
            rr = [r for r in rows if r["style"] == st and r["set"] == s]
            pk = np.array([r["nominal_peak_C"] for r in rr])
            ca = np.array([r["core_area_pct"] for r in rr])
            summ.append(dict(style=st, set=s, n=len(rr), peak_min_C=pk.min(), peak_max_C=pk.max(),
                             core_area_pct_min=ca.min(), core_area_pct_max=ca.max()))
    print(md_table(summ, "{:.3g}"))
    save_csv(OUT / "summary.csv", summ)
    save_json(OUT / "summary.json", summ)

    fig, axes = plt.subplots(2, 4, figsize=(13, 6.5))
    for col, st in enumerate([1, 2, 3, 4]):
        for row, fp in enumerate([f for f in gen if f.style == f"gen_Style_{st}"][:2]):
            ax = axes[row, col]
            for b, t in zip(fp.blocks, fp.types):
                c = {"big": "C0", "little": "C1", "fill": "0.9"}[t]
                ax.add_patch(plt.Rectangle((b.x * 1e3, b.y * 1e3), b.w * 1e3, b.h * 1e3, fc=c,
                                           ec="k", lw=0.5))
            W, Hd = fp.die
            ax.set(xlim=(0, W * 1e3), ylim=(0, Hd * 1e3), aspect="equal", title=fp.name)
            ax.grid(False)
    fig.suptitle("generated floorplans (blue = big, orange = little, grey = FILL)")
    fig.savefig(OUT / "examples.png")


if __name__ == "__main__":
    main()
