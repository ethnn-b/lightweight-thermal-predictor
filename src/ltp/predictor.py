"""predictor.py: the prediction stage. Needs only the model file and NumPy (no HotSpot).

A model file (.npz) written by `ltp calibrate` holds, for one floorplan:
  names, power_names       output blocks and power inputs, in order
  t_amb                    ambient (K)
  G                        S1 influence matrix (n_out x N)        -> steady
  A, tau                   T3 sum-of-exponentials (n_out x N x M) -> transient, forecast
  G_hot, hot_names         optional: S1-hot rows (hottest cell of each core)

    p = Predictor.load("model.npz")
    p.steady(P)                         T for power vector(s) P
    p.transient(P_trace, dt)            T trace from a cold chip (or from steady state of P0)
    p.forecast(T_now, P_hist, P_next, dt)   T for the next len(P_next) steps, anchored on sensors
"""
import numpy as np


class Predictor:
    def __init__(self, names, power_names, t_amb, G, A, tau, G_hot=None, hot_names=None):
        self.names, self.power_names = list(names), list(power_names)
        self.t_amb = float(t_amb)
        self.G = np.asarray(G, float)
        self.A = np.asarray(A, float)
        self.tau = np.asarray(tau, float)
        self.G_hot = None if G_hot is None else np.asarray(G_hot, float)
        self.hot_names = None if hot_names is None else list(hot_names)
        self._Af = self.A.reshape(self.A.shape[0], -1)

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path):
        d = np.load(path, allow_pickle=False)
        get = lambda k: d[k] if k in d.files else None   # noqa: E731
        return cls(d["names"], d["power_names"], d["t_amb"], d["G"], d["A"], d["tau"],
                   get("G_hot"), get("hot_names"))

    def save(self, path, **meta):
        extra = {} if self.G_hot is None else dict(G_hot=self.G_hot, hot_names=self.hot_names)
        np.savez(path, names=self.names, power_names=self.power_names, t_amb=self.t_amb,
                 G=self.G, A=self.A, tau=self.tau, **extra, **meta)

    def size_bytes(self):
        """Coefficients only: G (steady) + A, tau (transient)."""
        return int(8 * (self.G.size + self.A.size + self.tau.size))

    # ------------------------------------------------------------------ steady
    def steady(self, P):
        P = np.asarray(P, float)
        return self.t_amb + P @ self.G.T

    def steady_hot(self, P):
        """Hottest-cell temperature of each core (S1-hot), if calibrated."""
        return self.t_amb + np.asarray(P, float) @ self.G_hot.T

    # ------------------------------------------------------------------ transient (T3)
    def initial_state(self, P0=None):
        """Filter state: cold chip (P0 None) or the steady state of power P0."""
        N, M = self.A.shape[1], self.A.shape[2]
        return np.zeros((N, M)) if P0 is None else np.repeat(np.asarray(P0, float)[:, None], M, 1)

    def step(self, z, p, dt):
        """Advance the state by one step of power p; returns (z, T)."""
        lam = np.exp(-dt / self.tau)
        z = lam * z + (1 - lam) * np.asarray(p, float)[:, None]
        return z, self.t_amb + self._Af @ z.ravel()

    def transient(self, P, dt, z0=None):
        """Temperature trace for power trace P (rows = steps). Row k = end of step k."""
        P = np.asarray(P, float)
        lam = np.exp(-dt / self.tau)
        z = self.initial_state() if z0 is None else z0.copy()
        out = np.empty((len(P), self.A.shape[0]))
        for k in range(len(P)):
            z = lam * z + (1 - lam) * P[k][:, None]
            out[k] = self._Af @ z.ravel()
        return self.t_amb + out

    def run_state(self, P, dt, z0=None):
        """Filter state after the whole power history P (no outputs computed)."""
        P = np.asarray(P, float)
        lam = np.exp(-dt / self.tau)
        z = self.initial_state() if z0 is None else z0.copy()
        for p in P:
            z = lam * z + (1 - lam) * p[:, None]
        return z

    # ------------------------------------------------------------------ forecast
    def forecast(self, T_now, z_now, P_next, dt, idx=None):
        """Forecast temperatures for the next len(P_next) steps.

        z_now: model state after the power history (run_state / step);
        T_now: measured temperatures of outputs idx (default: all outputs) at this instant.
        The model's open-loop prediction is shifted so it starts at the measurement, which
        removes any bias that built up; the shift is kept constant over the horizon.
        """
        idx = slice(None) if idx is None else idx
        T_model_now = self.t_amb + self._Af @ z_now.ravel()
        traj = self.transient(P_next, dt, z0=z_now)
        return traj[:, idx] + (np.asarray(T_now, float) - T_model_now[idx])
