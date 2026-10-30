# P4-3 [OPT]: Leakage (temperature-dependent power)

**Question.** With leakage, power depends on temperature, so HotSpot is no longer linear. How
much does S1 degrade, and can a small correction fix it?

**Reproduce.** `bash experiments/run.sh P4-3_leakage` (a few minutes). Needs the 10× build:
`LTP_LEAK_ALPHA=1.5e+5 HOTSPOT_LTP=~/projects/HotSpot-leak10 bash setup/build_hotspot_ltp.sh`.

## Setup

- HotSpot's built-in leakage model (`-leakage_used 1`; steady state only, HotSpot does not
  support it in transient runs). Every block of the power layer, FILL included, leaks
  P_leak = α · area · e^(β (T − 383.15 K)), with α = 1.5×10⁴ W/m² and β = 0.036 /K. HotSpot
  iterates power and temperature to a fixed point (0.01 K tolerance).
- At our temperatures the default leakage is small (0.2–0.5 W per chip), so the test is repeated
  with **10× α** (a separate build, `HotSpot-leak10`): 2–5 W, about 3–5 % of the chip's power.
- Main subset, 50 random power vectors each.
- Predictors:
  - **S1 (no leakage):** the P1-1 model, unchanged.
  - **S1 + leakage loop:** T = T_amb + G_all (P + P_leak(T)), iterated from T = S1(P) until it
    changes by < 10⁻⁴ K. G_all is the influence of *every* block of the power layer (FILL too,
    since it also leaks): one extra steady run per FILL block (3–17 runs). The leakage formula is
    assumed known (it is a property of the technology, not of the floorplan).

## Results

| floorplan | leakage | leakage power (mean) | S1 without leakage: mean / max error | S1 + leakage loop: mean / max error | iterations | time per prediction |
|---|---|---|---|---|---|---|
| s1_fp001 | default | 0.27 W | 0.072 / 0.086 K | 5×10⁻⁶ / 2×10⁻⁵ K | 3 | 24 µs |
| s2_fp004 | default | 0.20 W | 0.063 / 0.076 K | 6×10⁻⁶ / 1×10⁻⁵ K | 3 | 22 µs |
| s3_fp002 | default | 0.40 W | 0.084 / 0.097 K | 7×10⁻⁶ / 2×10⁻⁵ K | 3 | 24 µs |
| s4_fp001 | default | 0.48 W | 0.093 / 0.104 K | 6×10⁻⁶ / 1×10⁻⁵ K | 3 | 25 µs |
| s1_fp001 | 10× | 2.7 W | 0.74 / 0.89 K | 8×10⁻⁶ / 2×10⁻⁵ K | 4 | 29 µs |
| s2_fp004 | 10× | 2.0 W | 0.64 / 0.77 K | 9×10⁻⁶ / 2×10⁻⁵ K | 4 | 33 µs |
| s3_fp002 | 10× | 4.1 W | 0.86 / 1.00 K | 2×10⁻⁵ / 5×10⁻⁵ K | 4 | 30 µs |
| s4_fp001 | 10× | 4.9 W | 0.96 / 1.07 K | 4×10⁻⁵ / 6×10⁻⁵ K | 4 | 32 µs |

## Conclusion

- **Ignoring leakage costs 0.06–0.1 K with HotSpot's default model and about 1 K with 10× stronger
  leakage.** The error is almost uniform over the chip (mean ≈ max), because most of the leaking
  area is white space spread over the whole die, and every watt also warms the shared sink.
  Larger, sparser dies (Style_3/4) leak more.
- **A fixed-point loop on the calibrated model removes the error completely** (back to 10⁻⁵ K, the
  output precision) in 3–4 iterations and about 25–30 µs: still roughly 10,000× faster than one
  HotSpot steady run. The system is still linear in the *total* power, so linear calibration
  stays valid; only the leakage term must be added.
- The loop needs the influence of the leaking blocks too (G_all: here 11–25 steady runs instead of
  8), or a simpler approximation such as lumping the white-space leakage into the package term.
- **Limits:** HotSpot only supports leakage in steady state, so the transient side was not tested.
  The same loop applies per time step in T3 (one extra matrix-vector product per iteration). With
  much stronger leakage the loop can diverge (thermal runaway), as in HotSpot itself.

## Files

- `results/results.csv`, `results/summary.json`, `results/log.txt`.
