"""models.py: the calibrated predictors (plan.md §3).

All temperatures are in kelvin. "Rise" x = T - T_amb. Inputs are power vectors over the
floorplan's power blocks (cores; FILL blocks are always 0 W). Outputs are all blocks of the power
layer in .flp order (cores and FILL), unless a model says otherwise.

Steady
  S1  SteadyG       T = T_amb + G P                         (N calibration runs)
Transient (all run at a fixed step dt; row k = temperature at the end of step k, as in HotSpot)
  T1  FirstOrderLag x_i[k+1] = a_i x_i[k] + (1 - a_i) (G P[k])_i
  T2  ARX           x[k+1] = sum_l A_l x[k+1-l] + sum_l B_l P[k-l], steady gain fixed to G
  T3  SumExp        step response s_ij(t) = sum_m a_ijm (1 - exp(-t / tau_m)), M shared tau_m
"""
import io

import numpy as np
from scipy.optimize import least_squares


def _nbytes(arrays, dtype=np.float64):
    return int(sum(np.asarray(a).size for a in arrays) * np.dtype(dtype).itemsize)


class Model:
    kind = "?"

    def coefficients(self):
        raise NotImplementedError

    def size_bytes(self, dtype=np.float64):
        """Bytes of the coefficients alone (what the predictor needs to run)."""
        return _nbytes(self.coefficients(), dtype)

    def save(self, path, **meta):
        np.savez(path, kind=self.kind, **self.state(), **meta)

    def file_bytes(self):
        buf = io.BytesIO()
        np.savez(buf, **self.state())
        return buf.getbuffer().nbytes


# --------------------------------------------------------------------------- steady
class SteadyG(Model):
    """S1: influence matrix. G[:, j] = rise of every output for 1 W in input j."""
    kind = "S1"

    def __init__(self, G, t_amb):
        self.G, self.t_amb = np.asarray(G, float), float(t_amb)

    @classmethod
    def calibrate(cls, unit_rises, t_amb):
        """unit_rises[j] = output rise (K) for a 1 W step in input j alone."""
        return cls(np.column_stack(unit_rises), t_amb)

    def steady(self, P):
        P = np.asarray(P, float)
        return self.t_amb + P @ self.G.T if P.ndim == 2 else self.t_amb + self.G @ P

    def coefficients(self):
        return [self.G]

    def state(self):
        return dict(G=self.G, t_amb=self.t_amb)


class CompressedG(Model):
    """S2: G_ij ~ c_i + D_ij. D keeps only each output's k+1 nearest inputs (self first); every
    other input j reaches output i through one 'package' term c_i (every watt warms the shared
    spreader and sink). c_i is the mean of the dropped G_ij, which makes S2 exact for uniform
    power and is the least-squares choice.

    Stored as: c (n_out), for each output the k+1 kept input indices and values.
    Size ~ n_out (k + 2) numbers (plus small integer indices).
    """
    kind = "S2"

    def __init__(self, c, idx, val, n_in, t_amb):
        self.c, self.idx, self.val = np.asarray(c, float), np.asarray(idx), np.asarray(val, float)
        self.n_in, self.t_amb = int(n_in), float(t_amb)

    @classmethod
    def calibrate(cls, G, centres, out_centres, k, t_amb):
        """G: (n_out, N) from the S1 runs; centres: (N, 2) input positions; out_centres:
        (n_out, 2)."""
        d = np.linalg.norm(out_centres[:, None, :] - centres[None, :, :], axis=2)
        idx = np.argsort(d, axis=1)[:, :k + 1]
        kept = np.zeros(G.shape, bool)
        np.put_along_axis(kept, idx, True, axis=1)
        dropped = np.where(kept, np.nan, G)
        c = np.nan_to_num(np.nanmean(dropped, axis=1)) if k + 1 < G.shape[1] else np.zeros(len(G))
        val = np.take_along_axis(G, idx, axis=1) - c[:, None]
        return cls(c, idx, val, G.shape[1], t_amb)

    @property
    def G(self):
        G = np.repeat(self.c[:, None], self.n_in, axis=1)
        np.put_along_axis(G, self.idx, self.c[:, None] + self.val, axis=1)
        return G

    def steady(self, P):
        P = np.asarray(P, float)
        if P.ndim == 2:
            return self.t_amb + P.sum(1)[:, None] * self.c + np.einsum("ik,nik->ni", self.val,
                                                                       P[:, self.idx])
        return self.t_amb + self.c * P.sum() + (self.val * P[self.idx]).sum(1)

    def coefficients(self):
        return [self.c, self.val]

    def size_bytes(self, dtype=np.float64):
        # values in dtype + indices as uint8 (N < 256)
        return _nbytes([self.c, self.val], dtype) + self.idx.size

    def state(self):
        return dict(c=self.c, idx=self.idx, val=self.val, n_in=self.n_in, t_amb=self.t_amb)


class LowRankG(Model):
    """S2-lr: G ~ U V^T of rank r (truncated SVD). Size r (n_out + N)."""
    kind = "S2lr"

    def __init__(self, U, V, t_amb):
        self.U, self.V, self.t_amb = np.asarray(U, float), np.asarray(V, float), float(t_amb)

    @classmethod
    def calibrate(cls, G, r, t_amb):
        u, s, vt = np.linalg.svd(G, full_matrices=False)
        return cls(u[:, :r] * s[:r], vt[:r].T, t_amb)

    @property
    def G(self):
        return self.U @ self.V.T

    def steady(self, P):
        P = np.asarray(P, float)
        return self.t_amb + (P @ self.V) @ self.U.T

    def coefficients(self):
        return [self.U, self.V]

    def state(self):
        return dict(U=self.U, V=self.V, t_amb=self.t_amb)


# --------------------------------------------------------------------------- transient
class FirstOrderLag(Model):
    """T1: every output relaxes to its S1 steady value with its own time constant tau_i."""
    kind = "T1"

    def __init__(self, G, tau, t_amb):
        self.G, self.tau, self.t_amb = np.asarray(G, float), np.asarray(tau, float), float(t_amb)

    @classmethod
    def calibrate(cls, G, t, S, t_amb):
        """t: sample times (s); S[j]: (len(t), n_out) rise for a 1 W step in input j."""
        tau = np.empty(G.shape[0])
        for i in range(G.shape[0]):
            y = np.concatenate([S[j][:, i] for j in range(len(S))])

            def resid(log_tau):
                return np.concatenate([G[i, j] * (1 - np.exp(-t / np.exp(log_tau[0])))
                                       for j in range(len(S))]) - y
            tau[i] = np.exp(least_squares(resid, [np.log(1.0)]).x[0])
        return cls(G, tau, t_amb)

    def transient(self, P, dt, x0=None):
        a = np.exp(-dt / self.tau)
        x = np.zeros(self.G.shape[0]) if x0 is None else np.asarray(x0, float).copy()
        target = np.asarray(P, float) @ self.G.T
        out = np.empty_like(target)
        for k in range(len(target)):
            x = a * x + (1 - a) * target[k]
            out[k] = x
        return self.t_amb + out

    def coefficients(self):
        return [self.G, self.tau]

    def state(self):
        return dict(G=self.G, tau=self.tau, t_amb=self.t_amb)


class SumExp(Model):
    """T3: step responses as sums of M exponentials with shared time constants.

    Runs as N*M first-order filters of the power (one per input and time constant):
        z_jm[k+1] = l_m z_jm[k] + (1 - l_m) P_j[k],  l_m = exp(-dt / tau_m)
        x[k+1]    = sum_jm a_ijm z_jm[k+1]
    which reproduces the fitted step response exactly at the sample times.
    """
    kind = "T3"

    def __init__(self, A, tau, t_amb):
        self.A = np.asarray(A, float)          # (n_out, n_in, M)
        self.tau = np.asarray(tau, float)      # (M,)
        self.t_amb = float(t_amb)

    @property
    def G(self):
        return self.A.sum(axis=2)

    @staticmethod
    def _solve_weights(G, t, Y, tau):
        """Least squares for a_ijm with sum_m a_ijm = G_ij. Y: (len(t), n_out, n_in)."""
        phi = 1 - np.exp(-t[:, None] / tau[None, :])                # (T, M)
        base = phi[:, -1]
        X = phi[:, :-1] - base[:, None]                             # (T, M-1)
        R = Y - base[:, None, None] * G[None]                       # (T, n_out, n_in)
        Rf = R.reshape(len(t), -1)
        if X.shape[1]:
            coef, *_ = np.linalg.lstsq(X, Rf, rcond=None)           # (M-1, n_out*n_in)
            A = np.empty(G.shape + (len(tau),))
            A[..., :-1] = np.moveaxis(coef.reshape((len(tau) - 1,) + G.shape), 0, -1)
            A[..., -1] = G - A[..., :-1].sum(-1)
            resid = Rf - X @ coef
        else:
            A = G[..., None].copy()
            resid = Rf
        return A, resid

    @classmethod
    def calibrate(cls, G, t, Y, M, t_amb, tau0=None):
        """Fit M shared time constants (variable projection) and the weights.

        t: sample times (s), ideally log-spaced; Y: (len(t), n_out, n_in) rise per watt.
        """
        if tau0 is None:
            tau0 = np.logspace(np.log10(3e-3), np.log10(30.0), M)

        def resid(log_tau):
            return cls._solve_weights(G, t, Y, np.sort(np.exp(log_tau)))[1].ravel()

        sol = least_squares(resid, np.log(tau0), method="trf", x_scale=1.0, max_nfev=200 * M)
        tau = np.sort(np.exp(sol.x))
        A, _ = cls._solve_weights(G, t, Y, tau)
        return cls(A, tau, t_amb)

    def step_response(self, t):
        """(len(t), n_out, n_in) rise per watt."""
        phi = 1 - np.exp(-np.asarray(t)[:, None] / self.tau[None, :])
        return np.einsum("tm,ijm->tij", phi, self.A)

    def transient(self, P, dt, z0=None):
        P = np.asarray(P, float)
        lam = np.exp(-dt / self.tau)                                 # (M,)
        n_in, M = self.A.shape[1], len(self.tau)
        z = np.zeros((n_in, M)) if z0 is None else z0.copy()
        Af = self.A.reshape(self.A.shape[0], n_in * M)
        out = np.empty((len(P), self.A.shape[0]))
        for k in range(len(P)):
            z = lam * z + (1 - lam) * P[k][:, None]
            out[k] = Af @ z.ravel()
        return self.t_amb + out

    def steady_state_z(self, P):
        """Filter state for a chip already at the steady state of power P."""
        return np.repeat(np.asarray(P, float)[:, None], len(self.tau), axis=1)

    def coefficients(self):
        return [self.A, self.tau]

    def state(self):
        return dict(A=self.A, tau=self.tau, t_amb=self.t_amb)


class ARX(Model):
    """T2: x[k] = sum_{l=1..na} A_l x[k-l] + sum_{l=0..nb-1} B_l P[k-l]
    (x[k] = rise at the end of step k, after power row P[k] was applied, as in HotSpot).

    Fitted by least squares on one calibration trace, with the steady gain fixed to G:
    (I - sum A)^-1 sum B = G. Written in deviations from the steady target G P[k]:
        x[k] - G P[k] = sum_l A_l (x[k-l] - G P[k]) + sum_{l>=1} B_l (P[k-l] - P[k])
    In open-loop use the past x are the model's own predictions (start: cold chip, x = 0).
    """
    kind = "T2"

    def __init__(self, A, B, G, t_amb):
        self.A = np.asarray(A, float)    # (na, n_out, n_out)
        self.B = np.asarray(B, float)    # (nb, n_out, n_in); B[0] implied by the gain constraint
        self.G, self.t_amb = np.asarray(G, float), float(t_amb)

    @classmethod
    def calibrate(cls, G, P, T, t_amb, na=2, nb=2, ridge=1e-9):
        """P: (K, n_in) calibration power trace; T: (K, n_out) HotSpot temperatures (cold start)."""
        x = np.asarray(T, float) - t_amb
        P = np.asarray(P, float)
        K, n = x.shape
        xs = np.vstack([np.zeros((max(na, nb), n)), x])             # x[-l] = 0 before the trace
        Ps = np.vstack([np.zeros((max(na, nb), P.shape[1])), P])
        o = max(na, nb)
        tgt = P @ G.T                                                 # G P[k]
        rows = []
        for l in range(1, na + 1):                                    # x[k-l], k = 0..K-1
            rows.append(xs[o - l: o - l + K] - tgt)
        for l in range(1, nb):
            rows.append(Ps[o - l: o - l + K] - P)
        X = np.hstack(rows)
        Y = x - tgt
        XtX = X.T @ X + ridge * np.eye(X.shape[1])
        W = np.linalg.solve(XtX, X.T @ Y).T                          # (n_out, features)
        A = np.stack([W[:, l * n:(l + 1) * n] for l in range(na)])
        Bs = [W[:, na * n + (l - 1) * P.shape[1]: na * n + l * P.shape[1]] for l in range(1, nb)]
        B0 = (np.eye(n) - A.sum(0)) @ G - sum(Bs, np.zeros_like(G))
        return cls(A, np.stack([B0, *Bs]), G, t_amb)

    def transient(self, P, dt=None, x_hist=None, p_hist=None):
        """x_hist / p_hist: past rises and powers, most recent first (default: cold chip, 0 W)."""
        P = np.asarray(P, float)
        na, nb, n = len(self.A), len(self.B), self.A.shape[1]
        xh = [np.zeros(n) for _ in range(na)] if x_hist is None else list(x_hist)
        ph = [np.zeros(P.shape[1]) for _ in range(nb)] if p_hist is None else list(p_hist)
        out = np.empty((len(P), n))
        for k in range(len(P)):
            ph = [P[k]] + ph[:-1]
            x = sum(self.A[l] @ xh[l] for l in range(na)) + sum(self.B[l] @ ph[l] for l in range(nb))
            xh = [x] + xh[:-1]
            out[k] = x
        return self.t_amb + out

    def coefficients(self):
        return [self.A, self.B]

    def state(self):
        return dict(A=self.A, B=self.B, G=self.G, t_amb=self.t_amb)
