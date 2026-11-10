"""P2-3: hot spots inside cores (S1-hot-max) and how far its matrix can be compressed.

P0-3 showed the hottest grid cell inside a core is several K above the core's average, which is
all S1 predicts. S1-hot-max predicts the hottest spot directly, with no new HotSpot runs:
  calibration: the 64x64 maps of the P1-1 unit runs give G_cells (4,096 cells x N cores), the rise
  of every grid cell per watt in each core. S1-hot-max keeps the rows of every cell inside a core
  and predicts, per core, the max over its cells of T_amb + G_cells[q] . P (exact, HotSpot is linear).
Then the S1-hot-max matrix (all cells of the 8 cores, about 115 kB) is compressed:
  - float32 / float16 coefficients;
  - drop dominated cells: a cell whose coefficients are all <= another cell's of the same core can
    never be the hottest for non-negative power (exact for any P >= 0);
  - drop cells dominated over the TA power range (exact while every core stays within its range);
  - a coarser grid (every 2nd or 4th cell in each direction);
  - low rank (truncated SVD).
Test: 60 random power vectors per floorplan (each core uniform in its range), all 23 TA floorplans,
against the true hottest cell of every core in HotSpot's 64x64 map.
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
ROWS = 64


def grid_job(fp, p):
    r = H.steady(fp, p, group=f"datasets/{fp.name}", grid_map=True, keep=False)
    cells = GM.block_cells(fp, ROWS, ROWS)
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


class HotMax:
    """Per-core max over a set of linear rows: T_hot[c] = T_amb + max_{q in core c} M[q] . P.
    M holds the rows of all cores one after the other; starts[c] is where core c's rows begin."""

    def __init__(self, M, owner):
        order = np.argsort(owner, kind="stable")
        self.M, owner = M[order], owner[order]
        self.starts = np.searchsorted(owner, np.arange(owner.max() + 1))
        # float16 is a storage format: compute in float32 (as a C implementation would)
        self.W = self.M.astype(np.float32) if self.M.dtype == np.float16 else self.M

    def predict(self, P):
        T = np.atleast_2d(P).astype(self.W.dtype) @ self.W.T
        return AMB + np.maximum.reduceat(T, self.starts, axis=1).astype(float)

    def size_bytes(self):
        return self.M.size * self.M.dtype.itemsize


class LowRank:
    def __init__(self, M, owner, r):
        U, s, Vt = np.linalg.svd(M, full_matrices=False)
        self.A, self.B = U[:, :r] * s[:r], Vt[:r]
        self.hm = HotMax(self.A @ self.B, owner)          # for prediction; stored size is A and B

    def predict(self, P):
        return self.hm.predict(P)

    def size_bytes(self):
        return 8 * (self.A.size + self.B.size)


def undominated(M, owner, lo=None, hi=None):
    """Rows that can be the max of their core. Row q is dropped if another row q' of the same core
    satisfies (M[q'] - M[q]) . P >= 0 for every allowed P: for P >= 0 that is M[q'] >= M[q]
    elementwise; over a box lo <= P <= hi it is sum_j min(d_j lo_j, d_j hi_j) >= 0."""
    keep = np.zeros(len(M), bool)
    for c in np.unique(owner):
        idx = np.where(owner == c)[0]
        R = M[idx]
        D = R[None, :, :] - R[:, None, :]                  # D[q, q'] = R[q'] - R[q]
        if lo is None:
            dom = (D >= 0).all(2)
        else:
            dom = np.minimum(D * lo, D * hi).sum(2) >= 0
        # q is dropped if dominated by some q' != q; among exact ties keep the first
        same = (np.abs(D) == 0).all(2)
        np.fill_diagonal(dom, False)
        tie_later = same & (np.arange(len(idx))[None, :] > np.arange(len(idx))[:, None])
        dom &= ~tie_later
        keep[idx] = ~dom.any(1)
    return keep


def coarse(cells_q, step):
    r, c = cells_q // ROWS, cells_q % ROWS
    return (r % step == 0) & (c % step == 0)


MODELS = ["S1 core average", "S1-hot-max (all cells)", "float32", "float16",
          "dominated cells dropped", "dominated cells dropped, float16",
          "dropped over the TA power range", "dropped over the TA power range, float16",
          "coarse grid 32x32", "coarse grid 16x16", "low rank r=2", "low rank r=4"]


def main():
    fps = F.ta_floorplans()
    cals = C.run_calibration_runs_many(fps)
    tests = grid_tests(fps)
    rows = []
    for fp in fps:
        cal = cals[fp.name]
        G, Gc = cal["G"], cal["G_cells"]
        core = fp.power_idx
        cells = GM.block_cells(fp, ROWS, ROWS)
        q = np.concatenate([cells[i] for i in core])
        owner = np.concatenate([np.full(len(cells[i]), k) for k, i in enumerate(core)])
        M = Gc[q]                                                  # S1-hot-max matrix
        lo, hi = fp.power_bounds()
        k0, k1 = undominated(M, owner), undominated(M, owner, lo, hi)
        ok = owner.copy()
        models = {
            "S1 core average": (lambda P_: AMB + np.atleast_2d(P_) @ G[core].T, 8 * len(core) * fp.n_power),
            "S1-hot-max (all cells)": HotMax(M, ok),
            "float32": HotMax(M.astype(np.float32), ok),
            "float16": HotMax(M.astype(np.float16), ok),
            "dominated cells dropped": HotMax(M[k0], ok[k0]),
            "dominated cells dropped, float16": HotMax(M[k0].astype(np.float16), ok[k0]),
            "dropped over the TA power range": HotMax(M[k1], ok[k1]),
            "dropped over the TA power range, float16": HotMax(M[k1].astype(np.float16), ok[k1]),
            "coarse grid 32x32": HotMax(M[coarse(q, 2)], ok[coarse(q, 2)]),
            "coarse grid 16x16": HotMax(M[coarse(q, 4)], ok[coarse(q, 4)]),
            "low rank r=2": LowRank(M, ok, 2),
            "low rank r=4": LowRank(M, ok, 4)}
        t = tests[fp.name]
        P, true_hot = t["P"], t["hot"]
        for name in MODELS:
            m = models[name]
            fn, size = (m if isinstance(m, tuple) else (m.predict, m.size_bytes()))
            pr = fn(P)
            err = pr - true_hot
            t_us = bench.time_call(fn, [(p,) for p in P[:20]], repeats=2000, warmup=100)[0] * 1e6
            rows.append(dict(floorplan=fp.name, style=fp.style, model=name, size_bytes=int(size),
                             cells_kept=int(m.M.shape[0]) if isinstance(m, HotMax) else None,
                             mae_K=float(np.abs(err).mean()), max_K=float(np.abs(err).max()),
                             under_K=float(-err.min()),
                             die_peak_err_K=float(np.abs(pr.max(1) - t["die_max"]).max()),
                             hottest_core_acc=float((pr.argmax(1) == true_hot.argmax(1)).mean()),
                             time_us=t_us))
        print(f"{fp.name}: {len(q)} cells in cores, {k0.sum()} not dominated, "
              f"{k1.sum()} not dominated over the power range", flush=True)
    save_csv(OUT / "all_results.csv", rows)
    summ = []
    for name in MODELS:
        rr = [r for r in rows if r["model"] == name]
        summ.append(dict(model=name, size_bytes_median=int(np.median([r["size_bytes"] for r in rr])),
                         mae_K_mean=float(np.mean([r["mae_K"] for r in rr])),
                         max_K_worst=float(np.max([r["max_K"] for r in rr])),
                         die_peak_err_K_worst=float(np.max([r["die_peak_err_K"] for r in rr])),
                         hottest_core_acc_min=float(np.min([r["hottest_core_acc"] for r in rr])),
                         time_us_median=float(np.median([r["time_us"] for r in rr]))))
    print(md_table(summ, "{:.3g}"))
    save_csv(OUT / "summary.csv", summ)
    save_json(OUT / "summary.json", dict(summary=summ))

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), layout="constrained")
    marks = {"S1 core average": "+", "S1-hot-max (all cells)": "*", "float32": "o", "float16": "o",
             "dominated cells dropped": "D", "dominated cells dropped, float16": "D",
             "dropped over the TA power range": "s", "dropped over the TA power range, float16": "s",
             "coarse grid 32x32": "^", "coarse grid 16x16": "^", "low rank r=2": "v", "low rank r=4": "v"}
    for ax, key, lab in ((axes[0], "mae_K_mean", "mean error (K)"),
                         (axes[1], "max_K_worst", "worst error (K)")):
        for k, s in enumerate(summ):
            ax.plot(s["size_bytes_median"] / 1e3, max(s[key], 1e-6), marks[s["model"]], ms=9,
                    color=f"C{k % 10}", label=s["model"])
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set(xlabel="model size (kB, median over floorplans)", ylabel=lab)
    axes[0].set_title("mean error vs true hottest cell")
    axes[1].set_title("worst error (23 floorplans x 60 vectors)")
    axes[1].legend(fontsize=7, loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.savefig(OUT / "size_vs_error.png")


if __name__ == "__main__":
    main()
