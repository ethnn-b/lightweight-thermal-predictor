# P5-1: The `ltp` package (calibrate, steady, transient, forecast, bench)

**Question.** Can both stages be used as plain commands by someone who did not write the code?

**Reproduce.** The commands below (inside WSL, from the repo root). Unit tests:
`python3 tests/test_models.py`.

## What is in the package

| file | role |
|---|---|
| `src/ltp/calibrate.py` | calibration stage: the 3N planned HotSpot runs (cached), log-time merge of step responses |
| `src/ltp/models.py` | S1, S2, S2-lr, T1, T2 (ARX), T3: `calibrate(...)`, `steady(...)`, `transient(...)`, `size_bytes()` |
| `src/ltp/predictor.py` | **the product**: `Predictor.load(model.npz)` then `steady`, `steady_hot`, `transient`, `forecast`, `step`; NumPy only, no HotSpot |
| `src/ltp/baselines.py` | S0 power blurring (uncalibrated baseline) |
| `src/ltp/bench.py` | prediction-time measurement used everywhere |
| `src/ltp/cli.py`, `__main__.py` | the command line |
| `tests/test_models.py` | 7 tests on a synthetic linear system (exact S1, T3 recovers known time constants, ARX, T1, S2, save/load, forecast) |

A model file holds S1 (G), T3 (A, τ; M = 4 by default), the hottest-cell rows for S1-hot, and the
block names: 8 kB for a TA floorplan.

## Commands (actual output, s4_fp001)

```
$ python3 -m src.ltp calibrate s4_fp001 -o model_s4_fp001.npz
calibrated s4_fp001: 24 HotSpot runs, 0.4 s; model 8032 B of coefficients -> model_s4_fp001.npz
```
(0.4 s because the 24 runs were cached from P1-1; uncached, it takes about 5 CPU-minutes.)
`<floorplan>` can also be any TA-style folder, e.g. `data/sample_dataset/2D_floorplans/Style_2/fp_003`.

```
$ python3 -m src.ltp steady model_s4_fp001.npz --power 20,20,8,8,8,8,8,8
Core_0_L0  Core_1_L0  Core_2_L0  Core_3_L0  Core_4_L0  Core_5_L0  Core_6_L0  Core_7_L0  FILL_0_L0 ...
66.313     67.214     68.344     67.488     69.297     68.614     68.760     67.769     59.501    ...   (°C)

$ python3 -m src.ltp steady model_s4_fp001.npz --ptrace data/sample_dataset/2D_floorplans/Style_4/fp_001/fp_001_steady.ptrace
(same numbers: the TA's own ptrace format is read directly)

$ python3 -m src.ltp transient model_s4_fp001.npz --ptrace <file.ptrace> --dt 0.001 --warm -o out.ttrace
(writes a HotSpot-style .ttrace in kelvin; --warm starts from the steady state of the first row,
 the default is a cold chip like HotSpot)

$ python3 -m src.ltp forecast model_s4_fp001.npz --history past.ptrace --temps T_now.txt --next plan.ptrace
(temperatures for the planned steps, anchored on the measured temperatures in T_now.txt, °C)

$ python3 -m src.ltp bench model_s4_fp001.npz s4_fp001
model model_s4_fp001.npz: 8032 B of coefficients (G 1600 B, T3 6432 B, M = 4)
steady    vs HotSpot on 302 vectors: MAE 5.19e-06 K, max 1.40e-05 K, 2.6 us per call
transient vs HotSpot on 2000 steps (1 ms): MAE 0.051 K, max 0.189 K, 3.5 us per step
```

`ltp bench` prints the three required metrics against stored HotSpot outputs (generated and cached
on first use). Final timing numbers must come from one machine (plan §13).

Python use:

```python
from src.ltp.predictor import Predictor
p = Predictor.load("model_s4_fp001.npz")
T = p.steady([20, 20, 8, 8, 8, 8, 8, 8])            # K, every block
z = p.run_state(P_history, dt=1e-3)                  # state after the power so far
T_next = p.forecast(T_sensors, z, P_plan, dt=1e-3)   # next len(P_plan) steps, anchored on sensors
```

## Tests

```
$ python3 tests/test_models.py
ok test_steady_exact
ok test_sumexp_recovers_time_constants
ok test_sumexp_transient_matches_step_response
ok test_arx_fits_linear_system
ok test_first_order_lag_converges_to_G
ok test_compressed_g_full_k_is_exact
ok test_predictor_roundtrip_and_forecast
```
(pytest is not installed in our WSL; the file also runs under pytest.)

## Conclusion

- Both stages are usable as commands; the predictor needs only NumPy and an 8 kB file.
- The TA's file formats are used directly (floorplan folders, `.ptrace`).
- Not done: a `pyproject.toml` / pip install (`python3 -m src.ltp` from the repo root is enough
  for the course), and a `--model T2` option (T3 is the shipped transient model, P1-2/P3-1).

## Files

- `results/cli_demo.txt` (full output of the commands above), `results/model_s4_fp001.npz`,
  `results/demo_out.ttrace`.
