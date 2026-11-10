"""Extended validation: S1 and T3 (M = 4) on 52 generated floorplans.

The 52 are the 40 generated floorplans of P0-5d (data/generated, gen_001..gen_010 per style) plus
12 new ones (gen_011..gen_013 per style), all made by src/sim/tagen.py. For each floorplan:
  - calibrate S1 (8 steady runs) and T3 M = 4 (all 24 runs of P1-1);
  - test against HotSpot on 302 steady power vectors (TA nominal, max, 300 random) for S1 and on
    one 2 s phase trace from a cold chip for T3 (the "short" test of P3-1);
  - record the calibration cost, the prediction time and the model size.
Models never see test data. Results are written after every batch, and every HotSpot result is
cached in $LTP_RUNS, so an interrupted run can simply be started again.

    bash experiments/run.sh extended_validation            # all 52 (about 2 h)
    bash experiments/run.sh extended_validation --dry      # the 4 floorplans cached by the smoke test
"""
import sys
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import hotspot as H, datasets, tagen
from src.ltp import calibrate as C, bench
from src.ltp.models import SteadyG, SumExp

OUT = results_dir(__file__)
DT, AMB = 1e-3, H.AMBIENT
PER_STYLE, BATCH, N_STEADY, M = 13, 12, 300, 4
DRY = "--dry" in sys.argv
# TA references (P2-1: S1 on 24 floorplans; P3-1: T3 M=4, 2 s traces on 24 floorplans)
REF = dict(s1_mae_K=6e-6, s1_max_K=3e-5, t3_mae_K=0.090, t3_max_K=0.30)


def metrics(pred, truth, core):
    p, t = pred[:, core], truth[:, core]
    e = np.abs(p - t)
    return dict(mae_K=float(e.mean()), max_K=float(e.max()),
                peak_err_K=float(np.abs(p.max(1) - t.max(1)).max()),
                hottest_acc=float((p.argmax(1) == t.argmax(1)).mean()))


def main():
    t_start = time.perf_counter()
    fps = tagen.generated(PER_STYLE)
    if DRY:
        fps = [f for f in fps if f.name in ("g1_gen001", "g2_gen001", "g3_gen001", "g4_gen001")]
    batches = [fps[i:i + BATCH] for i in range(0, len(fps), BATCH)]
    print(f"{len(fps)} floorplans in {len(batches)} batches of up to {BATCH}", flush=True)
    rows, phase = [], dict(calibration=0.0, steady_test=0.0, transient_test=0.0, evaluation=0.0)
    for bi, batch in enumerate(batches):
        t0 = time.perf_counter(); cals = C.run_calibration_runs_many(batch)
        phase["calibration"] += time.perf_counter() - t0
        t0 = time.perf_counter(); steady = datasets.steady_test_many(batch, n=N_STEADY)
        phase["steady_test"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        traces = datasets.traces_many([(fp, "phase", 2000, "short") for fp in batch], dt=DT)
        phase["transient_test"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        for fp, tr in zip(batch, traces):
            cal, core = cals[fp.name], fp.power_idx
            t, Y = C.merged_samples(cal)
            s1, t3 = SteadyG(cal["G"], AMB), SumExp.calibrate(cal["G"], t, Y, M, AMB)
            d = steady[fp.name]
            ms = metrics(s1.steady(d["P"]), d["T"], core)
            mt = metrics(t3.transient(tr["P"], DT), tr["T"], core)
            t_s1, _ = bench.time_call(lambda p: s1.steady(p), [(p,) for p in d["P"][:64]],
                                      repeats=2000, warmup=200)
            t_t3 = bench.time_per_step(lambda Pk, dt: t3.transient(Pk, dt), tr["P"], DT, repeats=3)
            W, Hd = fp.die
            rows.append(dict(
                floorplan=fp.name, style=fp.style.replace("gen_", ""), die_mm=f"{W*1e3:g}x{Hd*1e3:g}",
                core_area_pct=100 * float(fp.power_areas_mm2.sum()) / (W * Hd * 1e6),
                n_blocks=len(fp.names),
                s1_mae_K=ms["mae_K"], s1_max_K=ms["max_K"], s1_peak_err_K=ms["peak_err_K"],
                s1_hottest_acc=ms["hottest_acc"],
                t3_mae_K=mt["mae_K"], t3_max_K=mt["max_K"], t3_peak_err_K=mt["peak_err_K"],
                t3_hottest_acc=mt["hottest_acc"],
                s1_time_us=t_s1 * 1e6, t3_time_us_per_step=t_t3 * 1e6,
                s1_bytes=s1.size_bytes(), t3_bytes=t3.size_bytes(),
                calib_hotspot_cpu_s=float(cal["hotspot_s_steady"].sum() + cal["hotspot_s_transient"].sum()),
                calib_s1_only_cpu_s=float(cal["hotspot_s_steady"].sum())))
        phase["evaluation"] += time.perf_counter() - t0
        save_csv(OUT / "all_results.csv", rows)                    # checkpoint after every batch
        el = time.perf_counter() - t_start
        print(f"batch {bi + 1}/{len(batches)} done: {len(rows)} floorplans, {el / 60:.1f} min elapsed, "
              f"about {el / len(rows) * (len(fps) - len(rows)) / 60:.0f} min left", flush=True)

    # summary per style and overall
    summ = []
    for label, sel in [(s, [r for r in rows if r["style"] == s]) for s in sorted({r["style"] for r in rows})] \
            + [("all", rows)]:
        g = lambda k, f: float(f([r[k] for r in sel]))   # noqa: E731
        summ.append(dict(
            style=label, floorplans=len(sel),
            s1_mae_K_mean=g("s1_mae_K", np.mean), s1_max_K_worst=g("s1_max_K", np.max),
            s1_peak_err_K_worst=g("s1_peak_err_K", np.max), s1_hottest_acc_min=g("s1_hottest_acc", np.min),
            t3_mae_K_mean=g("t3_mae_K", np.mean), t3_max_K_worst=g("t3_max_K", np.max),
            t3_peak_err_K_worst=g("t3_peak_err_K", np.max), t3_hottest_acc_min=g("t3_hottest_acc", np.min),
            s1_time_us=g("s1_time_us", np.median), t3_time_us_per_step=g("t3_time_us_per_step", np.median),
            calib_hotspot_cpu_s_mean=g("calib_hotspot_cpu_s", np.mean),
            calib_s1_only_cpu_s_mean=g("calib_s1_only_cpu_s", np.mean)))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    total = time.perf_counter() - t_start
    save_json(OUT / "summary.json", dict(
        floorplans=len(rows), dry_run=DRY, summary=summ, reference_TA=REF, phase_wall_s=phase,
        total_wall_s=total, workers=int(__import__("src.sim.parallel", fromlist=["WORKERS"]).WORKERS)))
    print({k: round(v) for k, v in phase.items()}, f"total {total / 60:.1f} min")

    # figure: error of S1 and T3 per floorplan, grouped by style, against the TA references
    styles = sorted({r["style"] for r in rows})
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4))
    for a, key, ref, title in ((ax[0], "s1_mae_K", REF["s1_mae_K"], "S1 (steady), mean error"),
                               (ax[1], "t3_mae_K", REF["t3_mae_K"], "T3 M = 4 (2 s trace), mean error")):
        for i, s in enumerate(styles):
            v = np.array([r[key] for r in rows if r["style"] == s])
            a.scatter(i + rng.uniform(-0.15, 0.15, len(v)), v, s=14, alpha=0.6, lw=0)
            a.hlines(np.median(v), i - 0.3, i + 0.3, color="k", lw=1.5)
        a.axhline(ref, color="r", ls="--", lw=1, label=f"TA floorplans: {ref:g} K")
        a.set_yscale("log"); a.set_xticks(range(len(styles)), styles)
        a.set(ylabel="error vs HotSpot (K)", title=title); a.legend(fontsize=7)
        a.grid(axis="y", alpha=0.3)
    fig.savefig(OUT / "error_by_style.png")


if __name__ == "__main__":
    main()
