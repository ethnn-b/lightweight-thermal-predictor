"""Extended S1 validation: S1 (steady) on 200 generated floorplans, 15 test vectors each.

200 floorplans from src/sim/tagen.py, 50 per style (gen_001..gen_050; the generator is
deterministic, so gen_001..013 are the 52 of extended_validation). Per floorplan:
  - calibrate S1 from the 8 steady unit runs (1 W in one core at a time);
  - test against HotSpot on 15 steady vectors: TA nominal, max and 13 random (within TA ranges).
All HotSpot runs of a phase go into one worker pool. Results are cached in $LTP_RUNS.

    LTP_WORKERS=20 bash experiments/run.sh extended_validation_s1                  # 200 -> results/
    LTP_WORKERS=20 bash experiments/run.sh extended_validation_s1 --per-style 250  # 1000 -> results_1000/
    (run.sh tees its log to results/log.txt; for --per-style, redirect the log yourself)
"""
import sys
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import hotspot as H, datasets, tagen
from src.sim.parallel import pmap, WORKERS
from src.ltp import calibrate as C, bench
from src.ltp.models import SteadyG

AMB = H.AMBIENT
PER_STYLE = int(sys.argv[sys.argv.index("--per-style") + 1]) if "--per-style" in sys.argv else 50
N_RANDOM = 13          # 13 random + nominal + max = 15 test vectors
REF = dict(s1_mae_K=6.5e-6, s1_max_K=3.4e-5)   # extended_validation, 52 floorplans
OUT = results_dir(__file__)
if PER_STYLE != 50:                               # results/ holds the 200-floorplan run
    OUT = OUT.parent / f"results_{4 * PER_STYLE}"
    OUT.mkdir(exist_ok=True)


def calibrate_all(fps):
    """Steady unit runs for every floorplan in one pool; same cache as C.steady_unit_runs."""
    C.CACHE.mkdir(parents=True, exist_ok=True)
    path = lambda fp: C.CACHE / f"{fp.name}_steady.npz"   # noqa: E731
    out = {fp.name: dict(np.load(path(fp))) for fp in fps if path(fp).exists()}
    todo = [fp for fp in fps if fp.name not in out]
    res = pmap(C._steady_job, [dict(fp=fp, j=j) for fp in todo for j in range(fp.n_power)])
    k = 0
    for fp in todo:
        r = res[k:k + fp.n_power]
        k += fp.n_power
        cal = dict(G=np.column_stack([x["T"] - AMB for x in r]),
                   G_cells=np.stack([x["grid"].ravel() - AMB for x in r], axis=1),
                   hotspot_s_steady=np.array([x["wall_s"] for x in r]))
        np.savez(path(fp), **cal)
        out[fp.name] = cal
    return out


def duplicates(fps, cals):
    """Pairs whose 8x8 core influence matrices have the same sorted eigenvalues (same die):
    candidates for rotated or mirrored copies of one layout."""
    sig = {}
    for fp in fps:
        G = cals[fp.name]["G"][fp.power_idx]
        sig[fp.name] = (fp.die, np.sort(np.linalg.eigvals(G).real))
    names, pairs = list(sig), []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            (da, ea), (db, eb) = sig[a], sig[b]
            if len(ea) == len(eb) and sorted(da) == sorted(db) and np.allclose(ea, eb, rtol=1e-4):
                pairs.append((a, b))
    return pairs


def distinct_per_style(fps, pairs):
    """Number of distinct layouts per style after merging duplicate pairs (union-find)."""
    parent = {fp.name: fp.name for fp in fps}
    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for a, b in pairs:
        parent[root(a)] = root(b)
    out = {}
    for fp in fps:
        s = fp.style.replace("gen_", "")
        out.setdefault(s, set()).add(root(fp.name))
    return {s: len(v) for s, v in sorted(out.items())}


def main():
    t_start = time.perf_counter()
    t0 = time.perf_counter(); fps = tagen.generated(PER_STYLE); t_gen = time.perf_counter() - t0
    print(f"{len(fps)} floorplans ({t_gen:.0f} s to load/generate), {WORKERS} workers", flush=True)

    t0 = time.perf_counter(); cals = calibrate_all(fps); t_cal = time.perf_counter() - t0
    print(f"calibration done: {t_cal:.0f} s", flush=True)
    t0 = time.perf_counter(); steady = datasets.steady_test_many(fps, n=N_RANDOM)
    t_test = time.perf_counter() - t0
    print(f"steady tests done: {t_test:.0f} s", flush=True)

    rows = []
    for fp in fps:
        cal, core, d = cals[fp.name], fp.power_idx, steady[fp.name]
        s1 = SteadyG(cal["G"], AMB)
        pred, truth = s1.steady(d["P"])[:, core], d["T"][:, core]
        e = np.abs(pred - truth)
        t_s1, _ = bench.time_call(lambda p: s1.steady(p), [(p,) for p in d["P"]],
                                  repeats=500, warmup=50)
        W, Hd = fp.die
        rows.append(dict(
            floorplan=fp.name, style=fp.style.replace("gen_", ""), die_mm=f"{W*1e3:g}x{Hd*1e3:g}",
            core_area_pct=100 * float(fp.power_areas_mm2.sum()) / (W * Hd * 1e6),
            n_blocks=len(fp.names), n_test=len(d["P"]),
            s1_mae_K=float(e.mean()), s1_max_K=float(e.max()),
            s1_peak_err_K=float(np.abs(pred.max(1) - truth.max(1)).max()),
            s1_hottest_acc=float((pred.argmax(1) == truth.argmax(1)).mean()),
            s1_time_us=t_s1 * 1e6, s1_bytes=s1.size_bytes(),
            calib_s1_cpu_s=float(cal["hotspot_s_steady"].sum())))
    save_csv(OUT / "all_results.csv", rows)

    summ = []
    for label, sel in [(s, [r for r in rows if r["style"] == s]) for s in sorted({r["style"] for r in rows})] \
            + [("all", rows)]:
        g = lambda k, f: float(f([r[k] for r in sel]))   # noqa: E731
        summ.append(dict(
            style=label, floorplans=len(sel),
            s1_mae_K_mean=g("s1_mae_K", np.mean), s1_mae_K_worst=g("s1_mae_K", np.max),
            s1_max_K_worst=g("s1_max_K", np.max), s1_peak_err_K_worst=g("s1_peak_err_K", np.max),
            s1_hottest_acc_min=g("s1_hottest_acc", np.min), s1_time_us=g("s1_time_us", np.median),
            calib_s1_cpu_s_mean=g("calib_s1_cpu_s", np.mean)))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))

    dups = duplicates(fps, cals)
    distinct = distinct_per_style(fps, dups)
    print(f"possible duplicate pairs: {len(dups)}; distinct layouts per style: {distinct}, "
          f"total {sum(distinct.values())}")
    total = time.perf_counter() - t_start
    save_json(OUT / "summary.json", dict(
        floorplans=len(rows), test_vectors_per_floorplan=N_RANDOM + 2, summary=summ,
        reference_52=REF, possible_duplicates=dups, distinct_per_style=distinct, workers=WORKERS,
        wall_s=dict(generate=t_gen, calibration=t_cal, steady_test=t_test, total=total)))
    print(f"total {total / 60:.1f} min")

    styles = sorted({r["style"] for r in rows})
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4))
    for a, key, ref, title in ((ax[0], "s1_mae_K", REF["s1_mae_K"], "S1 mean error per floorplan"),
                               (ax[1], "s1_max_K", REF["s1_max_K"], "S1 worst error per floorplan")):
        for i, s in enumerate(styles):
            v = np.array([r[key] for r in rows if r["style"] == s])
            a.scatter(i + rng.uniform(-0.15, 0.15, len(v)), v, s=10, alpha=0.6, lw=0)
            a.hlines(np.median(v), i - 0.3, i + 0.3, color="k", lw=1.5)
        a.axhline(ref, color="r", ls="--", lw=1, label=f"52 floorplans: {ref:g} K")
        a.set_yscale("log"); a.set_xticks(range(len(styles)), styles)
        a.set(ylabel="error vs HotSpot (K)", title=f"{title} ({len(rows)} floorplans)")
        a.legend(fontsize=7); a.grid(axis="y", alpha=0.3)
    fig.savefig(OUT / "error_by_style.png")


if __name__ == "__main__":
    main()
