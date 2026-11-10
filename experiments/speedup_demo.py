"""Worked example of the speed-up claims: time HotSpot and our models on the same inputs.

Run inside WSL:  bash experiments/run.sh ../experiments  (or see the command in the chat)
    OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD:$PWD/experiments python3 experiments/speedup_demo.py
"""
import subprocess
import time

import numpy as np

from src.sim import floorplans as F, hotspot as H, powergen
from src.ltp import calibrate as C, bench
from src.ltp.models import SteadyG, SumExp

fp = F.get("s4_fp001")
print("HotSpot binary:", H.HOTSPOT)
print("floorplan:", fp.name, "| cores:", fp.n_power, "| blocks incl. FILL:", len(fp.names))

# ---- calibration (cached from P1-1; these are HotSpot runs done once, beforehand) ----
cal = C.run_calibration_runs(fp)
print(f"calibration cost (HotSpot, done once): {cal['hotspot_s_steady'].sum():.2f} s for "
      f"{len(cal['hotspot_s_steady'])} steady runs (S1); "
      f"{cal['hotspot_s_transient'].sum():.1f} s more for the step runs (T3)")

# ---- 1. STEADY ----------------------------------------------------------------------
P = powergen.random_steady(fp, 5, seed=12345)          # 5 fresh power vectors, never seen
hs_t, hs_T = [], []
for p in P:
    r = H.steady(fp, p, group="speedup_demo", keep=False)
    hs_t.append(r["wall_s"]); hs_T.append(r["T"])
hs_T = np.array(hs_T)

s1 = SteadyG(cal["G"], H.AMBIENT)
s1_T = s1.steady(P)
s1_t, _ = bench.time_call(s1.steady, [(p,) for p in P], repeats=10000)

core = fp.power_idx
print("\n=== STEADY (one power vector -> 8 core temperatures) ===")
print("vector 0 power (W):        ", np.round(P[0], 2))
print("HotSpot core temps (C):    ", np.round(hs_T[0, core] - 273.15, 4))
print("S1 core temps (C):         ", np.round(s1_T[0, core] - 273.15, 4))
print(f"max |S1 - HotSpot| over 5 vectors: {np.abs(s1_T[:, core] - hs_T[:, core]).max():.2e} K")
print("HotSpot wall time per run (s):", np.round(hs_t, 3), f"-> median {np.median(hs_t):.3f} s")
print(f"S1 time per call: {s1_t * 1e6:.2f} us (median of 10,000 calls)")
print(f"speed-up = {np.median(hs_t):.3f} s / {s1_t * 1e6:.2f} us = {np.median(hs_t) / s1_t:,.0f}x")

# how much of HotSpot's 0.24 s is just starting a process?  (time `true`, a no-op program)
t0 = time.perf_counter()
for _ in range(20):
    subprocess.run(["true"])
spawn = (time.perf_counter() - t0) / 20
print(f"(process start-up alone: {spawn * 1e3:.2f} ms, so it is not what makes HotSpot slow)")

# ---- 2. TRANSIENT -------------------------------------------------------------------
steps, dt = 1000, 1e-3
Pt = powergen.phase_trace(fp, steps, seed=777, max_phase=200)
r = H.transient(fp, Pt, dt, group="speedup_demo", keep=False)
t3 = C.merged_samples(cal)
t3 = SumExp.calibrate(cal["G"], *t3, 4, H.AMBIENT)
t3_T = t3.transient(Pt, dt)
t3_step = bench.time_per_step(t3.transient, Pt, dt, repeats=5)
err = t3_T[:, core] - r["T"][:, core]
print(f"\n=== TRANSIENT ({steps} steps of 1 ms, cold start) ===")
print(f"HotSpot (patched, LU cached) wall: {r['wall_s']:.2f} s -> {r['wall_s'] / steps * 1e3:.2f} ms/step"
      " (includes ~0.1-0.5 s set-up)")
print(f"T3 (M=4): {t3_step * 1e6:.2f} us/step, mean |err| {np.abs(err).mean():.3f} K, "
      f"max {np.abs(err).max():.3f} K")
print(f"speed-up vs patched HotSpot: {r['wall_s'] / steps / t3_step:,.0f}x")
print(f"speed-up vs stock HotSpot (~234 ms/step, P0-4: 70.1 s / 300 steps): "
      f"{0.234 / t3_step:,.0f}x")
