"""powergen.py: power inputs for calibration and testing (plan.md §4.2).

All power is assigned by core type (from block size), within the TA ranges:
big 10-20 W, little 5-10 W (L2/NoC on HET-A: 1-4 W). Every generator takes a seed, so any data
set can be regenerated exactly.
"""
import numpy as np


def random_steady(fp, n, seed):
    """n random power vectors, each core uniform in its range."""
    rng = np.random.default_rng(seed)
    lo, hi = fp.power_bounds()
    return lo + (hi - lo) * rng.random((n, fp.n_power))


def phase_trace(fp, steps, seed, min_phase=1, max_phase=2000, levels=4):
    """Workload-like trace: each core runs phases of random length (log-uniform between
    min_phase and max_phase steps) at one of `levels` DVFS-like levels between the bottom and
    the top of its range. Cores switch independently."""
    rng = np.random.default_rng(seed)
    lo, hi = fp.power_bounds()
    P = np.empty((steps, fp.n_power))
    grid = np.linspace(0.0, 1.0, levels)
    for j in range(fp.n_power):
        k = 0
        while k < steps:
            length = int(np.exp(rng.uniform(np.log(min_phase), np.log(max_phase))))
            P[k:k + length, j] = lo[j] + (hi[j] - lo[j]) * rng.choice(grid)
            k += length
    return P


def excitation_trace(fp, steps, seed, min_phase=1, max_phase=5000):
    """Calibration trace for T2 (ARX): like phase_trace but with continuous random levels over
    the whole range, so every core is excited independently at short and long time scales."""
    rng = np.random.default_rng(seed)
    lo, hi = fp.power_bounds()
    P = np.empty((steps, fp.n_power))
    for j in range(fp.n_power):
        k = 0
        while k < steps:
            length = int(np.exp(rng.uniform(np.log(min_phase), np.log(max_phase))))
            P[k:k + length, j] = rng.uniform(lo[j], hi[j])
            k += length
    return P
