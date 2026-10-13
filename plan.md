# Project plan: a lightweight temperature predictor built on HotSpot

**Course project:** *Thermal management: lightweight temperature predictor*.

**One-line pitch:** Build `ltp`, a small Python library and command-line tool that predicts the
temperatures HotSpot would compute, but thousands of times faster and with a model small
enough to run inside a floorplanner's search loop or a run-time thermal manager. HotSpot is the
*teacher* that generates training data and ground truth. The *predictor* is the product.

Read `hotspot_for_dummies.md` for terms. `lit_review.md` covers prior work on fast temperature
prediction and explains where each experiment comes from.

---

## 1. What exactly are we building?

### 1.1 Two use cases, two modes

A temperature predictor is only "lightweight" relative to a use. There are two typical uses,
so `ltp` has one mode for each:

| Mode | Who calls it | Fixed | Changes | Question it answers | Must be fast because |
|---|---|---|---|---|---|
| **R (run-time)** | Workload mapper, DTM, OS scheduler | Floorplan, package | Power every interval (e.g. 1–10 ms) | "If I run *this* mapping for the next 10 ms, how hot will each core get?" | It runs on the chip itself, every interval |
| **D (design-time)** | Floorplanner | Package | Floorplan *and* power | "If I put the blocks *here*, what is the peak temperature?" | A floorplanner evaluates thousands of candidate layouts |

Mode R is the classic meaning of "temperature predictor" in the thermal-management literature
(Coskun 2009, Yeo 2008, Zhang 2018; lit review §4). Mode D is the ML-surrogate line (ThermEDGe,
GCN, ThePlace; lit review §5). In each mode we compare a simple physics-based model against a
learned one.

### 1.2 Inputs and outputs

```
Mode R:  ltp.steady(model, P[N])                      ->  T[N]           (per block/core)
         ltp.forecast(model, T_history, P_next, k)    ->  T for the next k steps
Mode D:  ltp.predict(flp, P[N])                       ->  T[N] per block, 64×64 map, T_peak
Build:   ltp.fit(...)  ->  model file (.npz)
```

### 1.3 What "lightweight" means: our targets

These are *targets*, set from the literature, not promises. The report states whether each
was met.

| Property | Mode R target | Mode D target | HotSpot (measured on this PC) |
|---|---|---|---|
| Mean abs. error per block | ≤ 0.5 K | ≤ 1 K | (ground truth) |
| Error in T_peak | ≤ 1 K | ≤ 2 K | |
| Hottest block identified correctly | ≥ 95 % | ≥ 90 % | |
| Time per prediction (one CPU core) | ≤ 100 µs | ≤ 5 ms | ≈ 10 ms block; ≈ 1 s grid 64×64 |
| Model size | ≤ 100 kB | ≤ 5 MB | n/a |

We report accuracy, speed, model size and how many HotSpot runs each model needed to build.
Most papers report only the first two (lit review §7).

---

## 2. Research questions

1. **RQ1, fixed chip:** for a fixed floorplan, how accurately and how cheaply can simple
   linear models (influence matrix, autoregressive forecasters) predict HotSpot's steady
   and future temperatures?
2. **RQ2, new floorplans:** can a cheap model predict temperature for a floorplan it has never
   seen? Compare a physics kernel (power blurring), gradient boosting, and a small CNN.
3. **RQ3, robustness:** where does each predictor break (realistic unseen floorplans, a
   different heat sink)?
4. **RQ4, usefulness:** does the predictor lead to the *same decisions* as HotSpot, and how
   much faster?

---

## 3. The models

### Mode R (fixed floorplan)

| ID | Model | Needs | Expected behaviour | Source idea |
|---|---|---|---|---|
| R0 | **Persistence**: next T = current T | nothing | Good only at very short horizons; the minimum to beat | standard |
| R1 | **Influence matrix**: T = T_amb + R·P | N HotSpot runs (1 W in one block each) | Exact for steady state without leakage | superposition |
| R2 | **AR**: next T from the last few temperatures only (least squares) | one training trace | Fine within a workload phase, misses phase changes | Coskun 2009 (ARMA) |
| R3 | **ARX**: next T from the last few temperatures *and* power (least squares) | one training trace | Close to exact, since HotSpot is linear | system identification |
| R4 *(opt.)* | **Exact state-space** from HotSpot's internal R and C matrices, plus a reduced version | C helper linked to HotSpot | Exact; shows how small the model can get | MatEx (Pagani 2015) |

### Mode D (new floorplans)

| ID | Model | Needs | Expected behaviour | Source idea |
|---|---|---|---|---|
| D1 | **Power blurring**: power-density map convolved with a heat-spread kernel | ~5 HotSpot runs | Fast, no training; errors near die edges | Ziabari 2014 |
| D2 | **Gradient boosting** on per-block features (power density, area, distance to edge, neighbours' power, total power) | dataset | Cheap and explainable | Zhang 2018 |
| D3 | **Small CNN**, trained two ways: (a) power map → temperature map; (b) learns only the error of D1 ("hybrid") | dataset | Best accuracy; the hybrid should generalise better | ThermEDGe 2021 |

D3a and D3b are the same network and code; only the training target differs.

The final `ltp` ships the best model per mode. Expected (to be tested): **R3** for mode R and
**D3b** for mode D.

---

## 4. Ground truth and data

### 4.1 HotSpot settings
- Package: example1 config (ambient 45 °C). Leakage off unless stated.
- Mode R: block model, transient, 1 ms sampling interval.
- Mode D: grid model, steady state, 64×64 (confirmed in P0-3).

### 4.2 Floorplans
| Family | What | Count | Used for |
|---|---|---|---|
| **EV6** | The stock Alpha 21264 floorplan from example1 | 1 | Mode R; sanity checks |
| **16-core** | 4×4 grid of cores, one block per core | 1 | Mode R; Demo 1 |
| **Random** | Random floorplans from recursive cutting of the die, 8–30 blocks, die 8–20 mm | ~1,500 | Mode D train/val/test |
| **HotFloorplan-EV6** | HotFloorplan layouts of the EV6 blocks, different weights and seeds | ~20 | Mode D realistic test set (never trained on); Demo 2 |

### 4.3 Power
- **gcc.ptrace** (the only real-workload trace we have) for EV6.
- **Synthetic traces** for mode R: each core switches between idle, medium and busy power
  levels with random phase lengths, kept within EV6's realistic power densities
  (≈ 0.01–3 W/mm²). Different random seeds for training and test traces.
- **Mode D:** random per-block power, total 20–120 W, realistic densities.

### 4.4 Splits (fixed before training)
- Mode R: train on one set of traces, test on traces with different seeds and on gcc.
- Mode D: 70/15/15 train/val/test *by floorplan*. HotFloorplan-EV6 is test-only.

---

## 5. Experiments

**Difficulty:** ★ easy (run HotSpot, a short script, a plot). ★★ medium (new code or a model
to train, some debugging). ★★★ hard (a technique you'd need to learn first, or C-level work).
**[CORE]** = needed. **[OPT]** = only if time allows.

### Summary

| ID | Experiment | Type | Difficulty |
|---|---|---|---|
| P0-1 | Example1 reproduced | CORE | ★ (done) |
| P0-2 | Linearity checks | CORE | ★ |
| P0-3 | Grid resolution choice | CORE | ★ |
| P0-4 | Infrastructure scripts | CORE | ★★ |
| P1-1 | Steady state: influence matrix (R1) | CORE | ★ |
| P1-2 | Forecasting: persistence, AR, ARX (R0, R2, R3) | CORE | ★★ |
| P1-3 | Exact and reduced state-space (R4) | OPT | ★★★ |
| P2-1 | Mode D dataset | CORE | ★★ |
| P2-2 | Power blurring (D1) | CORE | ★★ |
| P2-3 | Gradient boosting (D2) | CORE | ★★ |
| P2-4 | Small CNN, direct and hybrid (D3) | CORE | ★★★ |
| P3-1 | Robustness: realistic floorplans, different heat sink | CORE | ★ |
| P3-2 | Few-shot fine-tuning on the new heat sink | OPT | ★★ |
| P3-3 | Leakage (nonlinear power) | OPT | ★★ |
| P4-1 | `ltp` package and command line | CORE | ★★ |
| P4-2 | Demo 1: which cores to switch on | CORE | ★ |
| P4-3 | Demo 2: ranking floorplans | CORE | ★ |
| P4-4 | Demo 3: closed-loop run-time management | OPT | ★★ |

### Phase P0: Ground truth you can trust

**P0-1 [CORE] ★ Example1 reproduced and understood.** *Done* (see `README_SETUP.md`).

**P0-2 [CORE] ★ Linearity checks.**
Scale all power by 0.5×, 2× and 3×; run two power patterns separately and together; zero power.
*Expect:* temperature rise scales exactly, patterns add up, zero power gives ambient.
*Why it matters:* this is what makes R1 and R3 work. If it holds, any later error in them is a
bug, not physics.

**P0-3 [CORE] ★ Grid resolution.**
EV6 with the block model and grid 16, 32, 64, 128. Error against grid 128, and runtime.
*Output:* the grid size for mode D (expected 64) and HotSpot's own accuracy-vs-time curve.

**P0-4 [CORE] ★★ Infrastructure.** Python scripts to run HotSpot and save everything
(`run_hotspot.py`), read its outputs (`parse.py`), generate floorplans (`flpgen.py`) and power
(`powergen.py`), and run many simulations in parallel with resume (`sweep.py`).

### Phase P1: Mode R, fixed floorplan

Cases: EV6 and the 16-core chip.

**P1-1 [CORE] ★ Steady state: influence matrix (R1).**
N runs with 1 W in one block each give the matrix R. Test on gcc and 1,000 random power vectors.
*Expect:* error ≈ 0 (≪ 0.01 K), microseconds per prediction.
*Output:* error and time table; heat map of R (which blocks heat which).

**P1-2 [CORE] ★★ Forecasting future temperature (R0, R2, R3).**
Fit AR and ARX by least squares on training traces. Forecast 1, 10 and 100 ms ahead on test
traces and on gcc.
*Expect:* ARX is close to exact, because HotSpot is linear. AR does well within a workload
phase but fails when power changes, because it can't see the change coming. Both beat
persistence beyond the shortest horizon.
*Output:* **error vs forecast horizon** plot (the main mode R result); time per forecast.

**P1-3 [OPT] ★★★ Exact and reduced state-space (R4).**
Write a small C helper that extracts HotSpot's internal R and C matrices, turn them into an
exact forecaster, then shrink it to a few states. *Output:* error vs model size.
Only worth it if P1-2's ARX turns out clearly inexact.

### Phase P2: Mode D, new floorplans

**P2-1 [CORE] ★★ Dataset.** ~1,500 random floorplans, each with random power, grid 64×64 steady
state (≈ 30 min in parallel). Plus ~20 HotFloorplan-EV6 layouts (≈ 90 s each). Saved as `.npz`.

**P2-2 [CORE] ★★ Power blurring (D1).**
Take the heat-spread kernel from a 1 W point source in HotSpot, then predict any floorplan by
convolution (with mirrored edges).
*Expect:* about 1–2 K in the middle of the die, worse at edges and corners.

**P2-3 [CORE] ★★ Gradient boosting (D2).** Per-block features, scikit-learn, tuned on the
validation set.

**P2-4 [CORE] ★★★ Small CNN (D3a direct, D3b hybrid).**
A small U-Net (< 1 M parameters, CPU training) trained once on temperature maps and once on the
error of D1.
*Expect:* D3b is the most accurate and generalises best, because the physics part carries over
to new layouts.
*Output:* results table for D1, D2, D3a, D3b: error, T_peak error, hottest-block accuracy,
ms per prediction, size.

### Phase P3: Robustness

**P3-1 [CORE] ★ Where does it break?** No new models, only new test data:
(a) mode D models on HotFloorplan-EV6 (realistic, never seen);
(b) all models on a different heat sink (`r_convec` changed), mode R and mode D.
*Expect:* physics-based models (R1, D1, D3b) cope best; purely learned ones degrade most.

**P3-2 [OPT] ★★ Few-shot fine-tuning.** Retrain the mode D models with 10 and 50 samples
from the new heat sink and measure how much accuracy comes back.

**P3-3 [OPT] ★★ Leakage.** Turn on temperature-dependent leakage, so HotSpot is no longer
linear. Measure how much R1 and R3 degrade. Linked to Prof. Kedia's FastCool work.

### Phase P4: The product and demonstrations

**P4-1 [CORE] ★★ Package `ltp`.** Commands `ltp fit`, `ltp predict`, `ltp forecast`;
models saved as `.npz`; a few tests against stored HotSpot outputs; a short README.

The demos are small scripts that show the predictor reaching the same decisions as HotSpot,
much faster. They are not full mappers or floorplanners.

**P4-2 [CORE] ★ Demo 1: which cores to switch on.** On the 16-core chip, choose which 4 cores
run a busy task. Score all 1,820 choices with `ltp` (R1) and with HotSpot.
*Report:* is the coolest choice the same? How long does each take?

**P4-3 [CORE] ★ Demo 2: ranking floorplans.** Rank the HotFloorplan-EV6 layouts plus some
random EV6 layouts by predicted T_peak (D3b) and by HotSpot.
*Report:* do the rankings agree (Spearman correlation), and is the best layout the same?

**P4-4 [OPT] ★★ Demo 3: closed-loop run-time management.** Every 10 ms, use `ltp.forecast`
(R3) to decide whether to move a task to a cooler core before a temperature limit is reached.

---

## 6. Evaluation rules

- **Metrics:** mean and max absolute error (K), T_peak error, hottest-block accuracy; error vs
  horizon for forecasts.
- **Speed:** median over many predictions, single CPU thread. HotSpot is timed the same way.
- **Baselines always shown:** persistence for mode R, power blurring for mode D.
- **Test sets are used once**, at the end.

---

## 7. Repository layout

```
Lightweight Thermal Predictor/
├── hotspot_for_dummies.md, lit_review.md, plan.md, README_SETUP.md
├── configs/        HotSpot configs (base + different heat sink)
├── floorplans/     ev6, 16-core, generated (generated ones git-ignored, regenerable by seed)
├── src/sim/        run_hotspot.py, parse.py, flpgen.py, powergen.py, sweep.py
├── src/ltp/        the product: models, fit/predict/forecast, command line
├── experiments/    one script per experiment
└── results/<exp>/  outputs, CSVs, figures
```

Simulations run in WSL Ubuntu for speed; results are copied back. Tools: NumPy/SciPy,
scikit-learn, PyTorch (CPU).

---

## 8. Order of work

| Step | Work | Deliverable |
|---|---|---|
| 1 | P0 | Trusted ground truth and scripts |
| 2 | P1-1, P1-2 | Mode R results; start the P2-1 dataset in the background |
| 3 | P2-2, P2-3, P2-4 | Mode D results table |
| 4 | P3-1, P4-1 | Robustness table; `ltp` usable from the command line |
| 5 | P4-2, P4-3; report and slides | Final product, demos, write-up |

**Minimum viable project** (if time is short): P0, P1-1, P1-2, P2-1, P2-2, P2-3, P3-1, P4-1,
P4-2. That skips the CNN (the only ★★★ core item) and still gives a complete predictor for
mode R and a physics-plus-ML baseline for mode D.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| No real workload power beyond gcc | Synthetic phase traces with realistic densities; ask the professor |
| HotSpot is not ground truth for real silicon | Say so plainly: we predict *HotSpot*, which is itself within about 1–2 °C of detailed tools |
| Random floorplans are unrealistic | Realistic test set (HotFloorplan-EV6) |
| The CNN takes too long to get working | It is the last core model; the minimum viable project doesn't need it |

---

## 10. Decisions needed from you

1. What exactly did the professor say about the scope? If only one mode is wanted, we drop the
   other and go deeper on the chosen one.
2. Is synthetic power acceptable, or is McPAT/CoMeT-generated power expected?
3. Deadline and team size, to decide which [OPT] items stay.
4. OK to start P0 now?
