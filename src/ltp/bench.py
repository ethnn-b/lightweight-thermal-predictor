"""bench.py: the prediction-time metric (docs/plan.md §6).

Median wall time per call over many calls after a warm-up, in one Python process on one thread,
Python overhead included. Set OPENBLAS_NUM_THREADS=1 / OMP_NUM_THREADS=1 before importing NumPy
for final numbers (experiments/run.sh does).
"""
import time

import numpy as np


def time_call(fn, args_list, repeats=10000, warmup=500):
    """Median and 90th-percentile seconds per call of fn(*args), cycling through args_list."""
    n = len(args_list)
    for k in range(warmup):
        fn(*args_list[k % n])
    t = np.empty(repeats)
    for k in range(repeats):
        a = args_list[k % n]
        t0 = time.perf_counter()
        fn(*a)
        t[k] = time.perf_counter() - t0
    return float(np.median(t)), float(np.percentile(t, 90))


def time_per_step(fn, P, dt, repeats=5):
    """Seconds per step of a transient model run over the whole trace P (median of repeats)."""
    fn(P[:100], dt)
    t = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn(P, dt)
        t.append((time.perf_counter() - t0) / len(P))
    return float(np.median(t))
