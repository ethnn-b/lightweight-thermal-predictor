"""P1-3: is per-floorplan calibration needed?

All 23 TA floorplans have the same 8 cores (2 big, 6 little) and the same power ranges; only the
layout differs. We compare the calibrated influence matrix S1 (P1-1) with predictors that get no
HotSpot runs on the target floorplan:
  (a) S0, power blurring: one generic heat-spread kernel from a single point-source run on a
      large reference die, convolved with the target's power map;
  (b) per core type: one self-heating value per type, and coupling as a function of distance per
      type pair, learned from the other floorplans;
  (c) transfer: another floorplan's G, cores matched by type and index
      (c1: within Style_4 - same 14x14 die, only positions differ; c2: s1_fp001's G everywhere);
  (d) geometry regression: ridge regression of log G_ij on geometric features (distance,
      distances to die edges, core sizes, die size, white space), leave-one-floorplan-out;
      (d2) the same with 40 generated TA-style floorplans (P0-5d) added to the training data;
      (d3) S0 times a learned correction exp(f(features, log S0)), trained on both sets.
All are tested on the same HotSpot steady test set: TA nominal, max, and 300 random vectors per
floorplan (src/sim/datasets.py). Errors are over cores only.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, datasets, tagen
from src.ltp import calibrate as C
from src.ltp.baselines import s0_kernel, G_s0

OUT = results_dir(__file__)
AMB = H.AMBIENT
TWINS = {"s3_fp004": "s3_fp005", "s3_fp005": "s3_fp004"}   # 90-degree rotations (P0-5)


# ------------------------------------------------------------------ geometry
def geometry(fp):
    bl = [fp.blocks[i] for i in fp.power_idx]
    W, Hd = fp.die
    cx = np.array([b.x + b.w / 2 for b in bl]) * 1e3
    cy = np.array([b.y + b.h / 2 for b in bl]) * 1e3
    edge = np.array([[b.x, b.y, W - b.x - b.w, Hd - b.y - b.h] for b in bl]) * 1e3   # mm
    side = np.array([b.w for b in bl]) * 1e3
    return dict(cx=cx, cy=cy, edge=edge, side=side, W=W * 1e3, H=Hd * 1e3,
                types=fp.power_types,
                fill=1 - fp.power_areas_mm2.sum() / (W * Hd * 1e6))


def pair_features(g, i, j):
    self_ = float(i == j)
    d = np.hypot(g["cx"][i] - g["cx"][j], g["cy"][i] - g["cy"][j]) if i != j else 1.0  # unused
    ei, ej = np.sort(g["edge"][i]), np.sort(g["edge"][j])
    bi, bj = float(g["types"][i] == "big"), float(g["types"][j] == "big")
    f = [1.0, self_, bi, bj, bi * bj,
         (1 - self_) * np.log(d), (1 - self_) / d, (1 - self_) * d,
         np.log1p(ei[0]), np.log1p(ei[1]), np.log1p(ej[0]), np.log1p(ej[1]),
         self_ * np.log1p(ei[0]), self_ * np.log1p(ei[1]),
         np.log(g["W"] * g["H"]), g["fill"], abs(np.log(g["W"] / g["H"]))]
    return np.array(f)


def features(fp):
    g = geometry(fp)
    n = fp.n_power
    return np.array([pair_features(g, i, j) for i in range(n) for j in range(n)])


# ------------------------------------------------------------------ baselines
def type_index_map(src_fp, dst_fp):
    """For each core of dst, the index of the core of src with the same type and rank."""
    m = []
    for t, rank in zip(dst_fp.power_types,
                       [dst_fp.power_types[:k].count(t) for k, t in enumerate(dst_fp.power_types)]):
        idx = [k for k, x in enumerate(src_fp.power_types) if x == t]
        m.append(idx[rank])
    return np.array(m)


def per_type_model(train, fp, g_cache):
    """Self-heating = mean over training floorplans per type; coupling = binned mean vs distance
    per (type_i, type_j)."""
    selfs = {"big": [], "little": []}
    pairs = {}
    for f in train:
        g = g_cache[f.name]["geo"]
        Gc = g_cache[f.name]["Gc"]
        for i, ti in enumerate(g["types"]):
            selfs[ti].append(Gc[i, i])
            for j, tj in enumerate(g["types"]):
                if i != j:
                    d = np.hypot(g["cx"][i] - g["cx"][j], g["cy"][i] - g["cy"][j])
                    pairs.setdefault((ti, tj), []).append((d, Gc[i, j]))
    g = geometry(fp)
    n = fp.n_power
    G = np.zeros((n, n))
    for i, ti in enumerate(g["types"]):
        for j, tj in enumerate(g["types"]):
            if i == j:
                G[i, i] = np.mean(selfs[ti])
            else:
                dd, gg = np.array(pairs[(ti, tj)]).T
                d = np.hypot(g["cx"][i] - g["cx"][j], g["cy"][i] - g["cy"][j])
                bins = np.arange(0, dd.max() + 1.0, 1.0)
                k = np.digitize(dd, bins)
                bc = np.array([dd[k == u].mean() for u in np.unique(k)])
                bg = np.array([gg[k == u].mean() for u in np.unique(k)])
                G[i, j] = np.interp(d, bc, bg)
    return G


def ridge_fit(X, y, lam=1e-3):
    mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0) + 1e-12
    Xs = np.hstack([X[:, :1], (X[:, 1:] - mu) / sd])
    w = np.linalg.solve(Xs.T @ Xs + lam * np.eye(Xs.shape[1]), Xs.T @ y)
    return lambda Xn: np.hstack([Xn[:, :1], (Xn[:, 1:] - mu) / sd]) @ w


# ------------------------------------------------------------------ evaluation
def evaluate(Gc, test, core):
    P, T = test["P"], test["T"][:, core]
    pred = AMB + P @ Gc.T
    err = pred - T
    return dict(mae_K=float(np.abs(err).mean()), max_K=float(np.abs(err).max()),
                peak_err_K=float(np.abs(pred.max(1) - T.max(1)).max()),
                hottest_acc=float((pred.argmax(1) == T.argmax(1)).mean()))


def main():
    fps = F.ta_floorplans()
    cals = C.run_calibration_runs_many(fps)                      # cached from P1-1
    tests = datasets.steady_test_many(fps, n=300)
    cache = {fp.name: dict(G=cals[fp.name]["G"], Gc=cals[fp.name]["G"][fp.power_idx],
                           geo=geometry(fp), X=features(fp)) for fp in fps}
    kernel = s0_kernel()
    np.savez(OUT / "s0_kernel.npz", r_mm=kernel[0], K_per_W=kernel[1])
    # 40 generated TA-style floorplans (P0-5d): extra training data for (d2); steady runs only
    gen = tagen.generated(10)
    gen_cache = {f.name: dict(Gc=C.steady_unit_runs(f)["G"][f.power_idx], X=features(f),
                              S0=G_s0(f, kernel)[f.power_idx]) for f in gen}
    for fp in fps:
        cache[fp.name]["S0"] = G_s0(fp, kernel)[fp.power_idx]

    rows = []
    for fp in fps:
        core = fp.power_idx
        test = tests[fp.name]
        Gc = cache[fp.name]["Gc"]
        res = {"S1 calibrated": evaluate(Gc, test, core)}
        res["(a) S0 power blurring"] = evaluate(cache[fp.name]["S0"], test, core)
        train = [f for f in fps if f.name != fp.name and f.name != TWINS.get(fp.name)]
        res["(b) per core type"] = evaluate(per_type_model(train, fp, cache), test, core)
        m = type_index_map(F.get("s1_fp001"), fp)
        if fp.name != "s1_fp001":
            res["(c2) transfer from s1_fp001"] = evaluate(
                cache["s1_fp001"]["Gc"][np.ix_(m, m)], test, core)
        Xtr = np.vstack([cache[f.name]["X"] for f in train])
        ytr = np.concatenate([np.log(cache[f.name]["Gc"].ravel()) for f in train])
        pred = ridge_fit(Xtr, ytr)(cache[fp.name]["X"])
        res["(d) geometry regression"] = evaluate(np.exp(pred).reshape(Gc.shape), test, core)
        Xtr2 = np.vstack([Xtr] + [g["X"] for g in gen_cache.values()])
        ytr2 = np.concatenate([ytr] + [np.log(g["Gc"].ravel()) for g in gen_cache.values()])
        pred2 = ridge_fit(Xtr2, ytr2)(cache[fp.name]["X"])
        res["(d2) geometry regression + 40 generated"] = evaluate(np.exp(pred2).reshape(Gc.shape),
                                                                   test, core)
        # (d3): learn only the correction to power blurring, log(G / G_S0), from all of them
        src = [cache[f.name] for f in train] + list(gen_cache.values())
        Xtr3 = np.vstack([np.hstack([c["X"], np.log(c["S0"].ravel())[:, None]]) for c in src])
        ytr3 = np.concatenate([np.log(c["Gc"].ravel() / c["S0"].ravel()) for c in src])
        X3 = np.hstack([cache[fp.name]["X"], np.log(cache[fp.name]["S0"].ravel())[:, None]])
        G3 = cache[fp.name]["S0"] * np.exp(ridge_fit(Xtr3, ytr3)(X3)).reshape(Gc.shape)
        res["(d3) S0 + learned correction"] = evaluate(G3, test, core)
        if fp.style == "Style_4":
            for src in fps:
                if src.style == "Style_4" and src.name != fp.name:
                    m = type_index_map(src, fp)
                    r = evaluate(cache[src.name]["Gc"][np.ix_(m, m)], test, core)
                    rows.append(dict(floorplan=fp.name, style=fp.style,
                                     method="(c1) transfer within Style_4", source=src.name, **r))
        for meth, r in res.items():
            rows.append(dict(floorplan=fp.name, style=fp.style, method=meth, source="", **r))
        print(fp.name, " ".join(f"{k.split(' ')[0]}={v['mae_K']:.3f}" for k, v in res.items()))

    save_csv(OUT / "all_results.csv", rows)
    methods = ["S1 calibrated", "(a) S0 power blurring", "(b) per core type",
               "(c1) transfer within Style_4", "(c2) transfer from s1_fp001",
               "(d) geometry regression", "(d2) geometry regression + 40 generated",
               "(d3) S0 + learned correction"]
    summ = []
    for meth in methods:
        rr = [r for r in rows if r["method"] == meth]
        summ.append(dict(method=meth, cases=len(rr),
                         mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                         mae_K_worst=float(np.max([r["mae_K"] for r in rr])),
                         max_K_worst=float(np.max([r["max_K"] for r in rr])),
                         peak_err_K_worst=float(np.max([r["peak_err_K"] for r in rr])),
                         hottest_acc_mean=float(np.mean([r["hottest_acc"] for r in rr])),
                         hottest_acc_worst=float(np.min([r["hottest_acc"] for r in rr]))))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    per_style = []
    for meth in methods:
        for st in ["Style_1", "Style_2", "Style_3", "Style_4"]:
            rr = [r for r in rows if r["method"] == meth and r["style"] == st]
            if rr:
                per_style.append(dict(method=meth, style=st,
                                      mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                                      max_K_worst=float(np.max([r["max_K"] for r in rr]))))
    save_csv(OUT / "per_style.csv", per_style)
    print(md_table(per_style, "{:.3g}"))
    save_json(OUT / "summary.json", dict(summary=summ, per_style=per_style))

    fig, ax = plt.subplots(figsize=(8, 3.6))
    data = [[r["mae_K"] for r in rows if r["method"] == m] for m in methods]
    ax.boxplot(data, showfliers=True)
    ax.set_yscale("log")
    ax.set_xticks(range(1, len(methods) + 1),
                  ["S1\ncalibrated", "(a) S0", "(b) per\ntype", "(c1) within\nStyle_4",
                   "(c2) from\ns1_fp001", "(d) geometry\nregression", "(d2) + 40\ngenerated",
                   "(d3) S0 +\ncorrection"], fontsize=7)
    ax.set(ylabel="mean abs error over cores (K), per floorplan",
           title="steady error without per-floorplan calibration vs S1")
    fig.savefig(OUT / "error_by_method.png")

    rb, kb = kernel
    fig, ax = plt.subplots(figsize=(4.5, 3))
    ax.plot(rb, kb)
    ax.set(xlabel="distance from a 1 W source (mm)", ylabel="temperature rise (K)",
           title="S0 heat-spread kernel (28 mm reference die)")
    fig.savefig(OUT / "s0_kernel.png")


if __name__ == "__main__":
    main()
