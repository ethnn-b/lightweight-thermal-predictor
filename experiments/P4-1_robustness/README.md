# P4-1: Where does the calibrated predictor break?

**Question.** The models were calibrated with 1 W steps (S1, T3) or one excitation trace (T2) at
Δt = 1 ms from a cold chip. Do they still hold for inputs unlike their calibration: power far
above the calibrated range, very bursty power, task migrations, another time step, a warm chip?

**Reproduce.** `bash experiments/run.sh P4-1_robustness` (about 30 min the first time; the HotSpot
runs are cached in `~/ltp_runs/P4-1/`).

## Setup

Main subset (4 floorplans). No new models: S1 and T3 (M = 4) from P1-1, T2 ARX (2,2) all blocks
from P1-2's 20 s trace. Each case is compared with HotSpot; errors over cores.

| case | input |
|---|---|
| (a) above range | 30 steady vectors at 0.9–1.5× and 1.8–3× the TA maximum (up to 60 W per big core); a 3 s trace at 2× |
| (b) bursty | every core switches level every 1–5 ms (3 s) |
| (c) task migration | one heavy task (top of range) hops to another core every 300 ms, big ↔ little; others idle at the bottom of their range (3 s) |
| (d) other Δt | HotSpot and the models at Δt = 0.1 ms (0.3 s) and 10 ms (10 s); T3 is simply re-discretised (T2 is tied to 1 ms) |
| (e) warm start | HotSpot starts from the steady state of the first power row (`-init_file`); the models start from their own steady state for that row |
| (ref) | an ordinary 3 s phase trace, for comparison |

## Results

| case | model | mean abs error | worst max error | worst max after the first 50 steps | largest rise |
|---|---|---|---|---|---|
| (ref) normal trace | T3 | 0.10 K | 0.32 K | 0.32 K | 28 K |
| | T2 | 0.20 K | 0.77 K | 0.77 K | |
| (a) steady at 1.5× max | S1 | 9×10⁻⁶ K | 3×10⁻⁵ K | | 51 K |
| (a) steady at 3× max | S1 | 2×10⁻⁵ K | 5×10⁻⁵ K | | 102 K |
| (a) transient at 2× | T3 | 0.21 K | 0.64 K | 0.64 K | 55 K |
| | T2 | 0.45 K | 1.94 K | 1.94 K | |
| (b) bursty 1–5 ms | T3 | 0.11 K | 0.44 K | 0.44 K | 27 K |
| | T2 | 0.22 K | 0.72 K | 0.72 K | |
| (c) task migration | T3 | 0.076 K | 0.31 K | 0.31 K | 23 K |
| | T2 | 0.17 K | 0.84 K | 0.84 K | |
| (d) Δt = 0.1 ms | T3 | 0.14 K | 2.16 K | 1.21 K | 23 K |
| (d) Δt = 10 ms | T3 | 0.079 K | 1.88 K | 0.89 K | 31 K |
| (e) warm start | T3 | 0.029 K | 2.01 K | 0.27 K | 34 K |
| | T2 | 0.074 K | 2.01 K | 0.49 K | |

## Conclusion

- **Power outside the calibration range is no problem.** S1 stays exact at 3× the TA maximum
  (rises of 100 K), and the transient errors scale with power: at 2× power T3's error doubles,
  so it stays about 1 % of the rise. This follows from linearity (P0-2). The coefficients do not
  depend on the power level, unlike a model trained on power samples.
- **Workload and mapping do not matter either.** Bursty power and task migration (including
  big ↔ little hops) are predicted as well as the normal trace (T3 ≤ 0.44 K worst). The
  coefficients describe the chip, not the workload (plan §3).
- **T2 is consistently about 2× worse than T3 in every case**, as in P3-1, but it does not break
  either. Its calibration trace was rich enough.
- **A different time step is the weak spot.** T3 is fitted to HotSpot's 1 ms backward-Euler
  responses. At 0.1 ms, HotSpot resolves sub-millisecond silicon dynamics that the 1 ms fit never
  saw (1.2 K worst after the start); at 10 ms, HotSpot's own single backward-Euler step per
  10 ms damps the fast modes differently from the exact exponentials (0.9 K). Mean errors stay
  small (0.08–0.14 K). **Recommendation: calibrate at the Δt the DTM controller will use**
  (calibration is cheap), rather than re-discretise.
- **Warm start:** after the first 50 ms the error is back to the normal level (0.27 K). The
  early 2 K comes from HotSpot itself: its `-init_file` warm start fills each block's grid cells
  with one uniform temperature, which is not quite the true steady state, so HotSpot shows a short
  transient that a true steady state would not have.

## Files

- `results/all_results.csv` (every floorplan × case × model), `results/summary.csv`,
  `results/summary.json`, `results/log.txt`.
