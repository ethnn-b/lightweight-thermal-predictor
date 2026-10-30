"""P3-4 [OPT]: exact state-space model from HotSpot's own matrices, then model-order reduction (T4).

A debug build of HotSpot (setup/patch_dump.py, ~/projects/HotSpot-dump) writes the grid model's
conductance matrix G (sparse, symmetric), capacitances C and the node power vector P. HotSpot's
transient step is backward Euler:  (C/h + G) T+ = C/h T + P.  With x = T - T_amb and
B[:, j] = P(1 W in core j) - P(0 W), the exact model is  C x' = -G x + B p,  y = W x
(W = HotSpot's cell-to-block averaging of layer 0). 16,396 states per floorplan.

Reduction (two stages, on the main subset):
  1. modal truncation: the 200 slowest modes of the symmetric pencil (G, C) (shift-invert eigsh);
  2. balanced truncation of that 200-state system (square-root method) to r states,
     backward-Euler discretised at h = 1 ms exactly like HotSpot;
  3. everything dropped (fast modes) as one first-order filter per (output, input) pair, whose
     gain makes the steady state exact and whose pole makes the first 1 ms step exact.
Checks: full-order simulation reproduces HotSpot; reduced models of order r = 1..64 are tested on
the two 10 s test traces (shared with P1-2/P3-1), with size and time per step.
"""
import os
import time
from pathlib import Path

import numpy as np
import scipy.linalg as sl
import scipy.sparse as sp
import scipy.sparse.linalg as spl

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, gridmap as GM, datasets
from src.ltp import calibrate as C_

OUT = results_dir(__file__)
DUMP_BIN = Path.home() / "projects" / "HotSpot-dump" / "hotspot"
DT = 1e-3
K_MODES = 200
ORDERS = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64]


def dump(fp, p, tag):
    d = H.RUNS / "P3-4" / fp.name / tag
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "P.txt").exists():
        os.environ["LTP_DUMP_DIR"] = str(d)
        saved, H.HOTSPOT = H.HOTSPOT, DUMP_BIN
        H.transient(fp, np.atleast_2d(p), DT, group="P3-4", keep=False)
        H.HOTSPOT = saved
        del os.environ["LTP_DUMP_DIR"]
    return d


def load_system(fp):
    d0 = dump(fp, np.zeros(fp.n_power), "zero")
    lines = (d0 / "G_csc.txt").read_text().split("\n")
    n, nnz = map(int, lines[0].split())
    colptr = np.array(lines[1:n + 2], np.int64)
    ri = np.array([l.split() for l in lines[n + 2:n + 2 + nnz]], float)
    G = sp.csc_matrix((np.ascontiguousarray(ri[:, 1]), np.ascontiguousarray(ri[:, 0].astype(np.int64)),
                       colptr), shape=(n, n))
    Cd = np.loadtxt(d0 / "C.txt")
    P0 = np.loadtxt(d0 / "P.txt")
    B = np.empty((n, fp.n_power))
    for j in range(fp.n_power):
        e = np.zeros(fp.n_power); e[j] = 1.0
        B[:, j] = np.loadtxt(dump(fp, e, f"unit{j}") / "P.txt") - P0
    W = np.zeros((len(fp.blocks), n))
    W[:, :4096] = GM.hotspot_weights(fp, 64, 64)
    return G, Cd, B, W


def simulate_full(G, Cd, B, W, P):
    lu = spl.splu((sp.diags(Cd / DT) + G).tocsc())
    x = np.zeros(G.shape[0])
    out = np.empty((len(P), W.shape[0]))
    for k, p in enumerate(P):
        x = lu.solve(Cd / DT * x + B @ p)
        out[k] = W @ x
    return out


class ReducedBE:
    """Reduced model, backward Euler like HotSpot, plus a fast-part filter:
        x+ = (I - hA)^-1 (x + h B p)                     r slow states
        u+ = a * u + (1 - a) * p   (elementwise, n_out x N)   everything the reduction dropped
        y  = C x+ + sum_j Ds_ij u_ij
    Ds is the dropped part's steady gain (so the steady state is exact) and a is chosen so that the
    first step after a power change is exact too (y1 = HotSpot's one-step response)."""

    def __init__(self, A, B, C, Gss, y1):
        M = np.linalg.inv(np.eye(len(A)) - DT * A)
        self.Ad, self.Bd, self.C = M, DT * M @ B, C
        self.Ds = Gss - C @ np.linalg.solve(-A, B)
        D1 = y1 - C @ self.Bd                               # dropped part of the first step
        ratio = np.divide(D1, self.Ds, out=np.ones_like(self.Ds), where=np.abs(self.Ds) > 1e-12)
        self.a = np.clip(1 - ratio, 0.0, 0.999)

    def transient(self, P):
        x = np.zeros(len(self.Ad))
        u = np.zeros(self.Ds.shape)
        out = np.empty((len(P), self.C.shape[0]))
        for k, p in enumerate(P):
            x = self.Ad @ x + self.Bd @ p
            u = self.a * u + (1 - self.a) * p[None, :]
            out[k] = self.C @ x + (self.Ds * u).sum(1)
        return out

    def size_bytes(self):
        return 8 * (self.Ad.size + self.Bd.size + self.C.size + self.Ds.size + self.a.size)


def psd_factor(M):
    """L with L L^T = M for a symmetric positive semi-definite M (robust to round-off)."""
    w, V = np.linalg.eigh((M + M.T) / 2)
    return V * np.sqrt(np.clip(w, 0, None))


def reduce(G, Cd, B, W, Gss, y1, r_list):
    s = 1 / np.sqrt(Cd)
    S = sp.diags(s) @ G @ sp.diags(s)
    mu, V = spl.eigsh(S.tocsc(), k=K_MODES, sigma=0, which="LM")
    order = np.argsort(mu)
    mu, V = mu[order], V[:, order]
    Bq = V.T @ (s[:, None] * B)                    # (K, N)
    Cq = (W * s[None, :]) @ V                      # (n_out, K)
    A = -np.diag(mu)
    # balanced truncation of the modal system
    Wc = sl.solve_continuous_lyapunov(A, -Bq @ Bq.T)
    Wo = sl.solve_continuous_lyapunov(A.T, -Cq.T @ Cq)
    Lc, Lo = psd_factor(Wc), psd_factor(Wo)
    U, hsv, Vt = np.linalg.svd(Lo.T @ Lc)
    models = {}
    for r in r_list:
        if hsv[r - 1] < 1e-12 * hsv[0]:          # beyond numerical rank: nothing left to add
            continue
        Sr = np.diag(hsv[:r] ** -0.5)
        T = Lc @ Vt[:r].T @ Sr
        Ti = Sr @ U[:, :r].T @ Lo.T
        Ar, Br, Cr = Ti @ A @ T, Ti @ Bq, Cq @ T
        models[r] = ReducedBE(Ar, Br, Cr, Gss, y1)
    return models, ReducedBE(A, Bq, Cq, Gss, y1), mu, hsv


def main():
    fps = [F.get(n) for n in F.MAIN_SUBSET]
    cals = C_.run_calibration_runs_many(fps)
    tests = datasets.traces_many([(fp, "phase", 10000, f"test{s}") for fp in fps for s in (0, 1)])
    rows, checks, spectra = [], [], {}
    for i, fp in enumerate(fps):
        core = fp.power_idx
        G, Cd, B, W = load_system(fp)
        Gss = W @ spl.splu(G.tocsc()).solve(B)                  # exact steady gain
        y1 = W @ spl.splu((sp.diags(Cd / DT) + G).tocsc()).solve(B)   # exact first BE step
        checks.append(dict(floorplan=fp.name, states=G.shape[0],
                           steady_gain_vs_S1_maxdiff=float(np.abs(Gss - cals[fp.name]["G"]).max())))
        t0 = time.perf_counter()
        models, modal, mu, hsv = reduce(G, Cd, B, W, Gss, y1, ORDERS)
        red_s = time.perf_counter() - t0
        spectra[fp.name] = dict(tau_s=(1 / mu).tolist(), hsv=hsv.tolist())
        for s in (0, 1):
            P, T = tests[2 * i + s]["P"], tests[2 * i + s]["T"]
            if s == 0:
                t0 = time.perf_counter()
                full = simulate_full(G, Cd, B, W, P) + H.AMBIENT
                full_s = (time.perf_counter() - t0) / len(P)
                checks[-1].update(full_order_vs_hotspot_maxdiff=float(np.abs(full - T).max()),
                                  full_order_ms_per_step=full_s * 1e3, reduction_s=red_s)
                pm = modal.transient(P) + H.AMBIENT
                checks[-1].update(modal200_vs_hotspot_maxdiff=float(np.abs(pm[:, core] - T[:, core]).max()))
            for r, m in models.items():
                t0 = time.perf_counter()
                pr = m.transient(P) + H.AMBIENT
                t_step = (time.perf_counter() - t0) / len(P)
                e = pr[:, core] - T[:, core]
                rows.append(dict(floorplan=fp.name, trace=s, order=r, mae_K=float(np.abs(e).mean()),
                                 max_K=float(np.abs(e).max()), size_bytes=m.size_bytes(),
                                 time_us_per_step=t_step * 1e6))
        print(fp.name, checks[-1])
    save_csv(OUT / "checks.csv", checks)
    save_csv(OUT / "all_results.csv", rows)
    summ = []
    for r in ORDERS:
        rr = [x for x in rows if x["order"] == r]
        if not rr:
            continue
        summ.append(dict(model=f"T4 r={r}", mae_K_mean=float(np.mean([x["mae_K"] for x in rr])),
                         max_K_worst=float(np.max([x["max_K"] for x in rr])),
                         size_bytes=int(np.median([x["size_bytes"] for x in rr])),
                         time_us_per_step=float(np.median([x["time_us_per_step"] for x in rr]))))
    save_csv(OUT / "summary.csv", summ)
    print(md_table(checks, "{:.3g}")); print(md_table(summ, "{:.3g}"))
    save_json(OUT / "summary.json", dict(checks=checks, summary=summ, spectra=spectra))

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    ax[0].loglog([s["size_bytes"] for s in summ], [s["max_K_worst"] for s in summ], "o-",
                 label="T4 (balanced truncation)")
    ax[0].set(xlabel="model size (bytes)", ylabel="worst max abs error (K)",
              title="T4: error vs reduced order")
    for s in summ:
        ax[0].annotate(s["model"].split()[1], (s["size_bytes"], s["max_K_worst"]), fontsize=6)
    for n, sp_ in spectra.items():
        ax[1].semilogy(sp_["hsv"][:40], ".-", label=n)
    ax[1].set(xlabel="index", ylabel="Hankel singular value", title="how many states matter")
    ax[1].legend(fontsize=7)
    fig.savefig(OUT / "t4_reduction.png")


if __name__ == "__main__":
    main()
