"""P2-2: layout effects across the 23 TA floorplans (no new HotSpot runs).

Reads the calibrated G of every TA floorplan (P1-1) and asks why coefficients differ between
floorplans that have the same cores and the same power:
  - self-heating G_ii vs core type and distance to the die edge;
  - coupling G_ij vs distance between cores;
  - the shared 'package' part (smallest coupling) vs die size;
  - peak temperature at nominal power vs white space and die size (the TA's remark that white
    space keeps the chip cool).
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H
from src.ltp import calibrate as C

OUT = results_dir(__file__)


def main():
    fps = F.ta_floorplans()
    cals = C.run_calibration_runs_many(fps)
    selfs, pairs, per_fp = [], [], []
    for fp in fps:
        G = cals[fp.name]["G"][fp.power_idx]
        bl = [fp.blocks[i] for i in fp.power_idx]
        W, Hd = (v * 1e3 for v in fp.die)
        c = np.array([[(b.x + b.w / 2) * 1e3, (b.y + b.h / 2) * 1e3] for b in bl])
        for i, (b, t) in enumerate(zip(bl, fp.power_types)):
            e = sorted([b.x * 1e3, b.y * 1e3, W - (b.x + b.w) * 1e3, Hd - (b.y + b.h) * 1e3])
            neigh = sum(G[i, j] for j in range(len(bl)) if j != i)
            selfs.append(dict(floorplan=fp.name, style=fp.style, core=fp.power_names[i], type=t,
                              edge1_mm=e[0], edge2_mm=e[1], G_self=G[i, i],
                              heat_from_others_at_1W_each=neigh))
            for j, tj in enumerate(fp.power_types):
                if j != i:
                    pairs.append(dict(floorplan=fp.name, style=fp.style, pair=f"{t}-{tj}",
                                      d_mm=float(np.linalg.norm(c[i] - c[j])), G_ij=G[i, j]))
        Tn = H.AMBIENT + G @ fp.nominal_power()
        big = [i for i, t in enumerate(fp.power_types) if t == "big"]
        lit = [i for i, t in enumerate(fp.power_types) if t == "little"]
        per_fp.append(dict(floorplan=fp.name, style=fp.style, die_mm2=W * Hd,
                           core_area_pct=100 * fp.power_areas_mm2.sum() / (W * Hd),
                           G_min=float(G.min()), G_self_big=float(np.mean(G[big, big])),
                           G_self_little=float(np.mean(G[lit, lit])),
                           peak_nominal_C=float(Tn.max() - 273.15),
                           mean_big_C=float(Tn[big].mean() - 273.15),
                           mean_little_C=float(Tn[lit].mean() - 273.15)))
    save_csv(OUT / "self_heating.csv", selfs)
    save_csv(OUT / "coupling.csv", pairs)
    save_csv(OUT / "per_floorplan.csv", per_fp)

    stats = []
    for t in ("big", "little"):
        v = np.array([s["G_self"] for s in selfs if s["type"] == t])
        stats.append(dict(quantity=f"self-heating G_ii, {t} cores (K/W)", min=v.min(),
                          max=v.max(), max_over_min=v.max() / v.min()))
    v = np.array([p["G_ij"] for p in pairs])
    stats.append(dict(quantity="coupling G_ij, all pairs (K/W)", min=v.min(), max=v.max(),
                      max_over_min=v.max() / v.min()))
    v = np.array([p["G_min"] for p in per_fp])
    stats.append(dict(quantity="package term min G per floorplan (K/W)", min=v.min(),
                      max=v.max(), max_over_min=v.max() / v.min()))
    v = np.array([p["peak_nominal_C"] for p in per_fp])
    stats.append(dict(quantity="peak core temperature at nominal power (C)", min=v.min(),
                      max=v.max(), max_over_min=np.nan))
    # correlations with white space
    cap = np.array([p["core_area_pct"] for p in per_fp])
    die = np.array([p["die_mm2"] for p in per_fp])
    pk = np.array([p["peak_nominal_C"] for p in per_fp])
    corr = dict(peak_vs_core_area_pct=float(np.corrcoef(cap, pk)[0, 1]),
                peak_vs_die_area=float(np.corrcoef(die, pk)[0, 1]),
                package_term_vs_die_area=float(np.corrcoef(die, [p["G_min"] for p in per_fp])[0, 1]))
    # self-heating vs edge distance correlation, per type
    for t in ("big", "little"):
        e = np.array([s["edge1_mm"] for s in selfs if s["type"] == t])
        g = np.array([s["G_self"] for s in selfs if s["type"] == t])
        corr[f"self_heating_{t}_vs_edge_distance"] = float(np.corrcoef(e, g)[0, 1])
    print(md_table(stats, "{:.3g}"))
    print(corr)
    save_json(OUT / "summary.json", dict(spread=stats, correlations=corr))

    fig, ax = plt.subplots(2, 2, figsize=(10, 7))
    for t, col in (("big", "C0"), ("little", "C1")):
        ss = [s for s in selfs if s["type"] == t]
        ax[0, 0].scatter([s["edge1_mm"] for s in ss], [s["G_self"] for s in ss], c=col, s=12, label=t)
    ax[0, 0].set(xlabel="distance from core to nearest die edge (mm)",
                 ylabel="self-heating G_ii (K/W)", title="self-heating: type and position")
    ax[0, 0].legend()
    for k, pr in enumerate(["big-big", "big-little", "little-big", "little-little"]):
        pp = [p for p in pairs if p["pair"] == pr]
        ax[0, 1].scatter([p["d_mm"] for p in pp], [p["G_ij"] for p in pp], s=5, alpha=0.5,
                         label=f"{pr} (heated core: {pr.split('-')[1]})")
    ax[0, 1].set(xlabel="centre-to-centre distance (mm)", ylabel="coupling G_ij (K/W)",
                 title="coupling decays with distance, then levels off", yscale="log")
    ax[0, 1].legend(fontsize=7)
    for st, mk in zip(["Style_1", "Style_2", "Style_3", "Style_4"], "osD^"):
        pp = [p for p in per_fp if p["style"] == st]
        ax[1, 0].scatter([p["die_mm2"] for p in pp], [p["G_min"] for p in pp], marker=mk, label=st)
        ax[1, 1].scatter([p["core_area_pct"] for p in pp], [p["peak_nominal_C"] for p in pp],
                         marker=mk, label=st)
    ax[1, 0].set(xlabel="die area (mm²)", ylabel="smallest coupling in G (K/W)",
                 title="shared package term shrinks on bigger dies")
    ax[1, 1].set(xlabel="cores / die area (%)", ylabel="hottest core at nominal power (°C)",
                 title="less white space -> hotter")
    ax[1, 0].legend(); ax[1, 1].legend()
    fig.tight_layout()
    fig.savefig(OUT / "layout_effects.png")


if __name__ == "__main__":
    main()
