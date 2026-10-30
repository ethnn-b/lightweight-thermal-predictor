"""P2-1: the steady predictor - S0 (uncalibrated), S1 (influence matrix), S2 (compressed G).

Test set (never used in calibration): TA nominal, max and 300 random power vectors per floorplan,
all 23 TA floorplans + HET-A, HotSpot grid 64x64 as reference. Reports the three metrics:
accuracy (cores), prediction time (median of 10,000 single-vector calls, one thread) and model
size (bytes of coefficients, float64 and float32).
S2 is also run on larger homogeneous floorplans (HOM-16, HOM-64), where model size matters.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, datasets
from src.sim import flpgen
from src.ltp import calibrate as C, bench
from src.ltp.baselines import G_s0
from src.ltp.models import SteadyG, CompressedG, LowRankG

OUT = results_dir(__file__)
AMB = H.AMBIENT
HOTSPOT_STEADY_S = 0.24        # P0-4: one grid 64x64 steady run


def centres(fp, idx=None):
    bl = fp.blocks if idx is None else [fp.blocks[i] for i in idx]
    return np.array([[b.x + b.w / 2, b.y + b.h / 2] for b in bl])


def metrics(pred, T, core):
    err = pred[:, core] - T[:, core]
    return dict(mae_K=float(np.abs(err).mean()), max_K=float(np.abs(err).max()),
                peak_err_K=float(np.abs(pred[:, core].max(1) - T[:, core].max(1)).max()),
                hottest_acc=float((pred[:, core].argmax(1) == T[:, core].argmax(1)).mean()))


def ensure_hom64():
    path = F.FLOORPLAN_DIR / "hom_64.flp"
    if not path.exists():
        flpgen.write_flp(flpgen.core_grid(8, 8, 2.0, 2.0), path, "HOM-64: 8x8 identical cores")
    return F.get("hom_64")


def main():
    fps = F.ta_floorplans() + [F.get("het_a")]
    cals = C.run_calibration_runs_many(fps)
    tests = datasets.steady_test_many(fps, n=300)
    rows, s2rows = [], []
    for fp in fps:
        G = cals[fp.name]["G"]
        core = fp.power_idx
        P, T = tests[fp.name]["P"], tests[fp.name]["T"]
        s1 = SteadyG(G, AMB)
        models = {"S0 power blurring": SteadyG(G_s0(fp), AMB), "S1 influence matrix": s1}
        for k in range(fp.n_power):
            models[f"S2 k={k}"] = CompressedG.calibrate(G, centres(fp, fp.power_idx), centres(fp),
                                                        k, AMB)
        for r in range(1, fp.n_power + 1):
            models[f"S2lr r={r}"] = LowRankG.calibrate(G, r, AMB)
        args = [(p,) for p in P[:50]]
        for name, m in models.items():
            r = dict(floorplan=fp.name, style=fp.style, model=name, **metrics(m.steady(P), T, core),
                     size_bytes=m.size_bytes())
            if name.startswith("S2"):
                s2rows.append(dict(r, k=int(name.split("=")[1]),
                                   variant="S2lr" if name.startswith("S2lr") else "S2"))
                if name not in ("S2 k=2", "S2lr r=2"):
                    continue
            r["time_us"] = bench.time_call(m.steady, args)[0] * 1e6
            rows.append(r)
        # float32 coefficients
        s1_32 = SteadyG(G.astype(np.float32), AMB)
        rows.append(dict(floorplan=fp.name, style=fp.style, model="S1 float32",
                         **metrics(s1_32.steady(P.astype(np.float32)).astype(float), T, core),
                         size_bytes=s1.size_bytes(np.float32),
                         time_us=bench.time_call(s1_32.steady,
                                                 [(p.astype(np.float32),) for p in P[:50]])[0] * 1e6))
        # batch prediction: all test vectors in one call
        t_batch = bench.time_call(s1.steady, [(P,)], repeats=2000, warmup=50)[0]
        rows.append(dict(floorplan=fp.name, style=fp.style, model=f"S1 batch of {len(P)}",
                         **metrics(s1.steady(P), T, core), size_bytes=s1.size_bytes(),
                         time_us=t_batch / len(P) * 1e6))
        s1row = [r for r in rows if r["floorplan"] == fp.name and r["model"] == "S1 influence matrix"]
        print(fp.name, f"S1 max err {s1row[0]['max_K']:.2e} K")

    save_csv(OUT / "all_results.csv", [{k: r.get(k, "") for k in rows[0]} for r in rows])
    summ = []
    for name in ["S0 power blurring", "S1 influence matrix", "S1 float32", "S2 k=2",
                 "S2lr r=2", "S1 batch of 302"]:
        rr = [r for r in rows if r["model"] == name]
        summ.append(dict(model=name, floorplans=len(rr),
                         mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                         max_K_worst=float(np.max([r["max_K"] for r in rr])),
                         peak_err_K_worst=float(np.max([r["peak_err_K"] for r in rr])),
                         hottest_acc_min=float(np.min([r["hottest_acc"] for r in rr])),
                         time_us_median=float(np.median([r["time_us"] for r in rr])),
                         size_bytes_median=int(np.median([r["size_bytes"] for r in rr])),
                         speedup_vs_hotspot=HOTSPOT_STEADY_S /
                         (float(np.median([r["time_us"] for r in rr])) * 1e-6)))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    per_style = []
    for st in ["Style_1", "Style_2", "Style_3", "Style_4", "own"]:
        for name in ["S0 power blurring", "S1 influence matrix", "S2 k=2"]:
            rr = [r for r in rows if r["model"] == name and r["style"] == st]
            per_style.append(dict(style=st, model=name,
                                  mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                                  max_K_worst=float(np.max([r["max_K"] for r in rr]))))
    save_csv(OUT / "per_style.csv", per_style)
    print(md_table(per_style, "{:.3g}"))

    # S2 on the TA floorplans: error vs k
    save_csv(OUT / "s2_ta.csv", s2rows)
    s2_ta = []
    for v, ks in (("S2", range(8)), ("S2lr", range(1, 9))):
        for k in ks:
            rr = [r for r in s2rows if r["k"] == k and r["variant"] == v]
            s2_ta.append(dict(variant=v, k_or_rank=k,
                              size_bytes=int(np.median([r["size_bytes"] for r in rr])),
                              max_K_worst=float(np.max([r["max_K"] for r in rr])),
                              mae_K_mean=float(np.mean([r["mae_K"] for r in rr]))))
    print(md_table(s2_ta, "{:.3g}"))

    # S2 on larger floorplans
    big = [F.get("hom_16"), ensure_hom64()]
    btests = datasets.steady_test_many(big, n=100)
    brows = []
    for fp in big:
        G = C.steady_unit_runs(fp)["G"]
        P, T = btests[fp.name]["P"], btests[fp.name]["T"]
        core = fp.power_idx
        s1 = SteadyG(G, AMB)
        brows.append(dict(floorplan=fp.name, N=fp.n_power, model="S1", k=fp.n_power - 1,
                          size_bytes=s1.size_bytes(), **metrics(s1.steady(P), T, core),
                          time_us=bench.time_call(s1.steady, [(p,) for p in P[:50]])[0] * 1e6))
        for k in [0, 1, 2, 4, 8, 12, 16, 24, 32]:
            if k >= fp.n_power:
                continue
            m = CompressedG.calibrate(G, centres(fp, fp.power_idx), centres(fp), k, AMB)
            brows.append(dict(floorplan=fp.name, N=fp.n_power, model="S2", k=k,
                              size_bytes=m.size_bytes(), **metrics(m.steady(P), T, core),
                              time_us=bench.time_call(m.steady, [(p,) for p in P[:50]])[0] * 1e6))
        for r in [1, 2, 4, 8, 12, 16, 24, 32]:
            if r >= fp.n_power:
                continue
            m = LowRankG.calibrate(G, r, AMB)
            brows.append(dict(floorplan=fp.name, N=fp.n_power, model="S2lr", k=r,
                              size_bytes=m.size_bytes(), **metrics(m.steady(P), T, core),
                              time_us=bench.time_call(m.steady, [(p,) for p in P[:50]])[0] * 1e6))
    save_csv(OUT / "s2_large.csv", brows)
    print(md_table(brows, "{:.3g}"))
    save_json(OUT / "summary.json", dict(summary=summ, s2_ta=s2_ta, s2_large=brows))

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    for v, mk in (("S2", "o-"), ("S2lr", "o--")):
        rr = [r for r in s2_ta if r["variant"] == v]
        ax[0].loglog([r["size_bytes"] for r in rr], [r["max_K_worst"] + 1e-7 for r in rr], mk,
                     color="C0", label=f"{v}, TA floorplans (N = 8), worst of 24")
    for c, fp in zip(("C1", "C2"), big):
        for v, mk in (("S2", "s-"), ("S2lr", "s--")):
            rr = [r for r in brows if r["floorplan"] == fp.name and r["model"] in (v, "S1")]
            rr = sorted(rr, key=lambda r: r["size_bytes"])
            ax[0].loglog([r["size_bytes"] for r in rr], [r["max_K"] + 1e-7 for r in rr], mk,
                         color=c, label=f"{v}, {fp.name} (N = {fp.n_power})")
    ax[0].set(xlabel="model size (bytes)", ylabel="max abs error, cores (K)",
              title="compressed G: accuracy vs size (solid: S2 neighbours, dashed: low rank)")
    ax[0].legend(fontsize=7)
    names = ["S0 power blurring", "S1 influence matrix", "S2 k=2"]
    ax[1].boxplot([[r["max_K"] + 1e-7 for r in rows if r["model"] == n] for n in names])
    ax[1].set_yscale("log")
    ax[1].set_xticks([1, 2, 3], ["S0\n(uncalibrated)", "S1\n(full G)", "S2\n(k = 2)"])
    ax[1].set(ylabel="max abs error per floorplan (K)", title="24 floorplans, 302 test vectors each")
    fig.savefig(OUT / "steady_accuracy.png")


if __name__ == "__main__":
    main()
