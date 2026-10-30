"""P2-3: hot spots inside cores (model S1-hot).

P0-3 showed the hottest grid cell inside a core is 3-4 K above the core's average, which is what
S1 predicts. S1-hot predicts the hottest spot directly:
  calibration (no new runs): from the 64x64 maps of the P1-1 unit runs, G_cells (cells x N).
  For each core, pick the cell that is hottest at TA nominal power; S1-hot is those rows of G_cells.
Compared, against the true hottest cell of every core in HotSpot's map:
  S1 core average (no correction), S1 + a constant offset per core (measured at nominal power),
  and S1-hot. Test: 60 random power vectors per floorplan, all 23 TA floorplans, with grid maps.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, gridmap as GM, powergen
from src.sim.parallel import pmap
from src.sim.datasets import CACHE, _seed
from src.ltp import calibrate as C, bench

OUT = results_dir(__file__)
AMB = H.AMBIENT
N_TEST = 60


def grid_job(fp, p):
    r = H.steady(fp, p, group=f"datasets/{fp.name}", grid_map=True, keep=False)
    cells = GM.block_cells(fp, 64, 64)
    g = r["grid"].ravel()
    return dict(T=r["T"], hot=np.array([g[cells[i]].max() for i in fp.power_idx]),
                hot_cell=np.array([cells[i][np.argmax(g[cells[i]])] for i in fp.power_idx]),
                die_max=g.max())


def grid_tests(fps):
    out, todo = {}, []
    for fp in fps:
        path = CACHE / f"gridtest_{fp.name}_{N_TEST}.npz"
        if path.exists():
            out[fp.name] = dict(np.load(path))
        else:
            todo.append((fp, path, powergen.random_steady(fp, N_TEST, _seed(fp.name, "gridtest"))))
    res = pmap(grid_job, [dict(fp=fp, p=p) for fp, _, P in todo for p in P])
    k = 0
    for fp, path, P in todo:
        rr = res[k:k + len(P)]; k += len(P)
        d = dict(P=P, T=np.array([r["T"] for r in rr]), hot=np.array([r["hot"] for r in rr]),
                 hot_cell=np.array([r["hot_cell"] for r in rr]),
                 die_max=np.array([r["die_max"] for r in rr]))
        np.savez(path, **d)
        out[fp.name] = d
    return out


def main():
    fps = F.ta_floorplans()
    cals = C.run_calibration_runs_many(fps)
    tests = grid_tests(fps)
    rows = []
    moved = []
    for fp in fps:
        cal = cals[fp.name]
        G, Gc = cal["G"], cal["G_cells"]
        core = fp.power_idx
        cells = GM.block_cells(fp, 64, 64)
        Pn = fp.nominal_power()
        map_n = Gc @ Pn
        hot_idx = np.array([cells[i][np.argmax(map_n[cells[i]])] for i in core])
        G_hot = Gc[hot_idx]                                     # (N, N)
        offset = map_n[hot_idx] - (G @ Pn)[core]                # per-core offset at nominal
        t = tests[fp.name]
        P, true_hot = t["P"], t["hot"]
        # candidate cells per core: the hottest cell of that core for each single heated core,
        # and at nominal power; S1-hot-max predicts the max over them (still linear per cell)
        cand = []
        for i in core:
            c = {int(cells[i][np.argmax(Gc[cells[i], j])]) for j in range(fp.n_power)}
            c.add(int(cells[i][np.argmax(map_n[cells[i]])]))
            cand.append(np.array(sorted(c)))
        n_cand = sum(len(c) for c in cand)
        hot_max = np.column_stack([(P @ Gc[c].T).max(1) for c in cand]) + AMB
        all_max = np.column_stack([(P @ Gc[cells[i]].T).max(1) for i in core]) + AMB
        n_all = sum(len(cells[i]) for i in core)
        preds = {"S1 core average": AMB + P @ G[core].T,
                 "S1 + offset (nominal)": AMB + P @ G[core].T + offset,
                 "S1-hot (hottest cell)": AMB + P @ G_hot.T,
                 "S1-hot-max (candidate cells)": hot_max,
                 "all cells of each core": all_max}
        sizes = {"S1 core average": 8 * len(core) * fp.n_power,
                 "S1 + offset (nominal)": 8 * len(core) * (fp.n_power + 1),
                 "S1-hot (hottest cell)": 8 * len(core) * fp.n_power,
                 "S1-hot-max (candidate cells)": 8 * n_cand * fp.n_power,
                 "all cells of each core": 8 * n_all * fp.n_power}
        for name, pr in preds.items():
            err = pr - true_hot
            rows.append(dict(floorplan=fp.name, style=fp.style, model=name,
                             size_bytes=sizes[name],
                             mae_K=float(np.abs(err).mean()), max_K=float(np.abs(err).max()),
                             die_peak_err_K=float(np.abs(pr.max(1) - t["die_max"]).max()),
                             hottest_core_acc=float((pr.argmax(1) == true_hot.argmax(1)).mean())))
        moved.append(dict(floorplan=fp.name,
                          frac_hot_cell_moved=float((t["hot_cell"] != hot_idx[None]).mean()),
                          die_max_vs_max_core_cell_K=float(np.abs(t["die_max"] - true_hot.max(1)).max())))
    save_csv(OUT / "all_results.csv", rows)
    save_csv(OUT / "hot_cell_movement.csv", moved)
    summ = []
    for name in ["S1 core average", "S1 + offset (nominal)", "S1-hot (hottest cell)",
                 "S1-hot-max (candidate cells)", "all cells of each core"]:
        rr = [r for r in rows if r["model"] == name]
        summ.append(dict(model=name, size_bytes_median=int(np.median([r["size_bytes"] for r in rr])),
                         mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                         max_K_worst=float(np.max([r["max_K"] for r in rr])),
                         die_peak_err_K_worst=float(np.max([r["die_peak_err_K"] for r in rr])),
                         hottest_core_acc_min=float(np.min([r["hottest_core_acc"] for r in rr]))))
    print(md_table(summ, "{:.3g}"))
    mv = np.array([m["frac_hot_cell_moved"] for m in moved])
    print(f"hottest cell moved away from the calibrated cell in {100 * mv.mean():.1f}% of "
          f"(core, test vector) cases (worst floorplan {100 * mv.max():.1f}%)")
    G_hot_bytes = 8 * 8 * 8
    save_csv(OUT / "summary.csv", summ)
    save_json(OUT / "summary.json", dict(summary=summ, hot_cell_moved_mean=float(mv.mean()),
                                         hot_cell_moved_max=float(mv.max()),
                                         extra_bytes_S1_hot=G_hot_bytes))

    fig, ax = plt.subplots(figsize=(7, 3.4))
    names = [s["model"] for s in summ]
    ax.boxplot([[r["max_K"] for r in rows if r["model"] == n] for n in names])
    ax.set_yscale("log")
    ax.set_xticks([1, 2, 3, 4, 5], ["S1 core\naverage", "S1 + offset\n(at nominal)",
                                    "S1-hot\n(one cell)", "S1-hot-max\n(candidates)",
                                    "all cells\n(exact)"])
    ax.set(ylabel="max error vs true hottest cell (K)", title="predicting the hottest spot of each core")
    fig.savefig(OUT / "hot_spot_error.png")


if __name__ == "__main__":
    main()
