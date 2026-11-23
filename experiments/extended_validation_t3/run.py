"""Extended T3 validation: T3 (M = 4) on 100 generated floorplans, no steady test.

100 floorplans from src/sim/tagen.py, 25 per style (gen_001..gen_025), a subset of the 500 used by
extended_validation_s1 (S1 is already validated there, so this run only checks the transient model).
The generator is deterministic, so gen_001..013 are the 52 floorplans of extended_validation; their
calibration and test traces are reused from the cache in $LTP_RUNS. For each floorplan:
  - calibrate T3 M = 4 from all 24 runs of P1-1 (8 steady unit runs give G, 16 step responses give
    the exponentials);
  - test against HotSpot on one 2 s phase trace from a cold chip (the "short" test of P3-1), the
    same test as extended_validation;
  - record the calibration cost, the prediction time per step and the model size.
Models never see test data. Results are written after every batch, and every HotSpot result is
cached in $LTP_RUNS, so an interrupted run can simply be started again.

    bash experiments/run.sh extended_validation_t3                    # 100 floorplans -> results/
    bash experiments/run.sh extended_validation_t3 --per-style 50     # 200 -> results_200/
    (run.sh tees its log to results/log.txt; for --per-style, redirect the log yourself)
"""
import sys
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import hotspot as H, datasets, tagen
from src.ltp import calibrate as C, bench
from src.ltp.models import SumExp

DT, AMB, M, BATCH = 1e-3, H.AMBIENT, 4, 12
PER_STYLE = int(sys.argv[sys.argv.index("--per-style") + 1]) if "--per-style" in sys.argv else 25
OUT = results_dir(__file__)
if PER_STYLE != 25:
    OUT = OUT.parent / f"results_{4 * PER_STYLE}"
    OUT.mkdir(exist_ok=True)
# References: P3-1 (T3 M=4, 2 s traces, 24 TA floorplans) and extended_validation (52 generated)
REF = dict(TA=dict(t3_mae_K=0.090, t3_max_K=0.30), EV52=dict(t3_mae_K=0.0909, t3_max_K=0.340))


def metrics(pred, truth, core):
    p, t = pred[:, core], truth[:, core]
    e = np.abs(p - t)
    return dict(mae_K=float(e.mean()), max_K=float(e.max()),
                peak_err_K=float(np.abs(p.max(1) - t.max(1)).max()),
                hottest_acc=float((p.argmax(1) == t.argmax(1)).mean()))


def main():
    t_start = time.perf_counter()
    fps = tagen.generated(PER_STYLE)
    batches = [fps[i:i + BATCH] for i in range(0, len(fps), BATCH)]
    print(f"{len(fps)} floorplans ({PER_STYLE} per style) in {len(batches)} batches of up to {BATCH}, "
          f"T3 M = {M} only", flush=True)
    rows, phase = [], dict(calibration=0.0, transient_test=0.0, evaluation=0.0)
    for bi, batch in enumerate(batches):
        t0 = time.perf_counter(); cals = C.run_calibration_runs_many(batch)
        phase["calibration"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        traces = datasets.traces_many([(fp, "phase", 2000, "short") for fp in batch], dt=DT)
        phase["transient_test"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        for fp, tr in zip(batch, traces):
            cal, core = cals[fp.name], fp.power_idx
            t, Y = C.merged_samples(cal)
            t3 = SumExp.calibrate(cal["G"], t, Y, M, AMB)
            mt = metrics(t3.transient(tr["P"], DT), tr["T"], core)
            t_t3 = bench.time_per_step(lambda Pk, dt: t3.transient(Pk, dt), tr["P"], DT, repeats=3)
            W, Hd = fp.die
            rows.append(dict(
                floorplan=fp.name, style=fp.style.replace("gen_", ""), die_mm=f"{W*1e3:g}x{Hd*1e3:g}",
                core_area_pct=100 * float(fp.power_areas_mm2.sum()) / (W * Hd * 1e6),
                n_blocks=len(fp.names),
                t3_mae_K=mt["mae_K"], t3_max_K=mt["max_K"], t3_peak_err_K=mt["peak_err_K"],
                t3_hottest_acc=mt["hottest_acc"], t3_time_us_per_step=t_t3 * 1e6,
                t3_bytes=t3.size_bytes(),
                calib_hotspot_cpu_s=float(cal["hotspot_s_steady"].sum() + cal["hotspot_s_transient"].sum())))
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
            t3_mae_K_mean=g("t3_mae_K", np.mean), t3_mae_K_worst=g("t3_mae_K", np.max),
            t3_max_K_worst=g("t3_max_K", np.max), t3_peak_err_K_worst=g("t3_peak_err_K", np.max),
            t3_hottest_acc_min=g("t3_hottest_acc", np.min),
            t3_time_us_per_step=g("t3_time_us_per_step", np.median),
            calib_hotspot_cpu_s_mean=g("calib_hotspot_cpu_s", np.mean)))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(summ, "{:.3g}"))
    total = time.perf_counter() - t_start
    save_json(OUT / "summary.json", dict(
        floorplans=len(rows), per_style=PER_STYLE, model=f"T3 M={M}", summary=summ, reference=REF,
        phase_wall_s=phase, total_wall_s=total,
        workers=int(__import__("src.sim.parallel", fromlist=["WORKERS"]).WORKERS)))
    print({k: round(v) for k, v in phase.items()}, f"total {total / 60:.1f} min")

    # figure: T3 mean and worst error per floorplan, grouped by style, against the references
    styles = sorted({r["style"] for r in rows})
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4))
    for a, key, title in ((ax[0], "t3_mae_K", "T3 M = 4 (2 s trace), mean error"),
                          (ax[1], "t3_max_K", "T3 M = 4 (2 s trace), worst error")):
        for i, s in enumerate(styles):
            v = np.array([r[key] for r in rows if r["style"] == s])
            a.scatter(i + rng.uniform(-0.15, 0.15, len(v)), v, s=14, alpha=0.6, lw=0)
            a.hlines(np.median(v), i - 0.3, i + 0.3, color="k", lw=1.5)
        a.axhline(REF["TA"][key], color="r", ls="--", lw=1, label=f"TA floorplans: {REF['TA'][key]:g} K")
        a.set_xticks(range(len(styles)), styles)
        a.set(ylabel="error vs HotSpot (K)", title=title); a.legend(fontsize=7)
        a.grid(axis="y", alpha=0.3)
    fig.savefig(OUT / "error_by_style.png")


if __name__ == "__main__":
    main()
