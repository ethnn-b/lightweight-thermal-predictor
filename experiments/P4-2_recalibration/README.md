# P4-2 [OPT]: Recalibration after a package change

**Question.** The coefficients belong to one floorplan *and* one package (heat sink, ambient).
What happens if the package changes, and what does recalibration cost? (IC-ThermBench varies
ambient temperature and convection the same way; `docs/dataset.md` §2.)

**Reproduce.** `bash experiments/run.sh P4-2_recalibration` (about 30 min; 144 HotSpot
calibration runs).

## Setup

- s1_fp001 and s4_fp001. Three package changes, one at a time:
  - ambient 35 °C instead of 45 °C;
  - heat-sink convection resistance ×2 (`r_convec` 0.1 → 0.2 K/W, a worse cooler);
  - convection resistance ×0.5 (0.05 K/W, a better cooler).
- Tests under the new package: 50 random steady vectors and a 3 s phase trace (Δt = 1 ms, cold
  start), in HotSpot.
- Models: the old (base-package) S1 and T3 (M = 4), used with the old or the new ambient; and
  models recalibrated with the same 3N = 24 runs as P1-1 under the new package.

## Results

Max error over cores (K) under the new package:

| change | floorplan | model | steady max | transient max (3 s) | transient mean |
|---|---|---|---|---|---|
| ambient 35 °C | s1_fp001 | old model, old ambient | 10.0 | 10.2 | 9.93 |
| | | **old model, new T_amb** | **2×10⁻⁵** | 0.27 | 0.12 |
| | | recalibrated | 2×10⁻⁵ | 0.27 | 0.12 |
| | s4_fp001 | old model, old ambient | 10.0 | 10.2 | 9.98 |
| | | **old model, new T_amb** | **1×10⁻⁵** | 0.23 | 0.051 |
| | | recalibrated | 1×10⁻⁵ | 0.23 | 0.051 |
| r_convec ×2 | s1_fp001 | old model | **8.5** | 0.48 | 0.23 |
| | | recalibrated | 1×10⁻⁵ | 0.29 | 0.11 |
| | s4_fp001 | old model | **8.5** | 0.43 | 0.15 |
| | | recalibrated | 2×10⁻⁵ | 0.26 | 0.042 |
| r_convec ×0.5 | s1_fp001 | old model | **4.4** | 0.42 | 0.15 |
| | | recalibrated | 2×10⁻⁵ | 0.22 | 0.096 |
| | s4_fp001 | old model | **4.4** | 0.48 | 0.17 |
| | | recalibrated | 2×10⁻⁵ | 0.20 | 0.056 |

Recalibration cost: 24 HotSpot runs per floorplan (1,200–3,000 CPU-s here, with several
calibrations running in parallel; about 5 CPU-minutes on an idle machine, as in P1-1).

## Conclusion

- **A change of ambient temperature needs no recalibration.** The model predicts the rise above
  ambient, so the old coefficients with the new T_amb are exactly as good as recalibrated ones
  (identical errors). Forgetting to update T_amb is a 10 K error.
- **A change of heat sink does need recalibration.** The old coefficients are 8.5 K off in steady
  state when the convection resistance doubles, and 4.4 K when it halves. Recalibration with the
  usual 24 runs brings the error back to 10⁻⁵ K.
- **The error shows up slowly in transients.** Over a 3 s trace from a cold chip the old model is
  only 0.4–0.5 K off, because the heat sink takes tens of seconds to warm up (P1-1). After a long
  run, the full steady-state error applies, so a DTM controller would drift.
- **The error is almost exactly ΔR × total power** (0.1 K/W × ~85 W ≈ 8.5 K; 0.05 K/W × ~87 W
  ≈ 4.4 K) and the same on both floorplans. That suggests a convection change mainly adds the
  same amount to every steady coefficient (the shared package term of P2-2). If so, a sink change
  could be corrected *without* any HotSpot runs (G + ΔR·11ᵀ). This was not tested here; the
  transient part would still need refitting.

## Files

- `results/results.csv`, `results/summary.json`, `results/log.txt`.
