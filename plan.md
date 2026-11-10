# Project plan: a lightweight temperature predictor (calibrate once, predict fast)

**Course project:** *Thermal management: lightweight temperature predictor*.

**One-line pitch:** Build `ltp`, a small Python library and command-line tool that works in two
stages. **Calibration** runs HotSpot a small number of times on a given heterogeneous floorplan
and fits a compact set of coefficients. **Prediction** then uses only those coefficients to give
steady-state or transient temperatures for any power input, thousands of times faster than
HotSpot and with a model of a few kilobytes. HotSpot is the *reference* used for calibration and
for checking accuracy. The *calibrated predictor* is the product.

This file is the short plan. `hotspot_for_dummies.md` is the beginner's companion: Part A
explains every concept used here, and Part B goes through each experiment (why, what you need to
know, steps, what you should see). `docs/literature_review_and_references.md` covers prior work and explains where each
model comes from. `dataset.md` describes the TA's sample dataset and the two works the TAs
pointed to (IC-ThermBench, ATPlace2.5D). `Scope_Document.pdf` is the scope we submitted; this
plan stays inside it.

**Revision of 30 Oct 2026 (TA dataset).** The TAs gave us 23 heterogeneous 2D floorplans in
HotSpot format. They are now the main floorplans (§4.1), with the TA's power ranges (§4.2) and
HotSpot's grid model, as in the TA's instructions. The models and the phases are unchanged. Using
the data, P0-3, P0-5 and P1-3 are stronger, and P2-2 (layout effects) and P2-3 (hot spots inside
cores) are new. See §14 for the full list of changes.

---

## 0. The problem statement, and where this plan answers it

> Develop a lightweight temperature predictor. Two stages:
> **Calibration** (one-time per floorplan): tune predictor coefficients as per given floorplan
> for heterogeneous cores.
> **Predictor**: predict the temperature (steady state or transient) for a given power input.
> **Metrics:** predictor accuracy, prediction time, model size.
> **Wishlist:** show the effectiveness of the predictor for proactive DTM.

| Requirement | Where it is handled |
|---|---|
| Calibration, one-time per floorplan | §1.2, models in §3, Phase P1 |
| Given floorplan, heterogeneous cores | The TA's 23 big/little floorplans (§4.1, `dataset.md`); P1-3 shows why per-floorplan calibration is needed |
| Predict steady state | Models S0–S2, Phase P2 |
| Predict transient | Models T0–T4, Phase P3 |
| For a given power input | API in §1.3; test power in §4.2 |
| Accuracy, prediction time, model size | Defined in §1.4 and §6; every result table reports all three |
| Wishlist: proactive DTM | Phase P6 |

Work from the earlier plan that does not serve these stages (learned predictors for floorplans
never seen before: gradient boosting, CNN, the 1,500-floorplan dataset) has been moved to §11,
*Out of scope*. Power blurring stays, as the uncalibrated baseline.

---

## 1. What exactly are we building?

### 1.1 The two stages

```
            ONE-TIME, PER FLOORPLAN                         MANY TIMES, FAST
 ┌──────────────────────────────────────────┐     ┌──────────────────────────────────────┐
 │ CALIBRATION                              │     │ PREDICTOR                            │
 │ floorplan.flp + package config           │     │ model.npz + power input P            │
 │   -> a few planned HotSpot runs          │ ──► │   -> steady T[N]       (S models)    │
 │   -> fit coefficients                    │     │   -> transient T[k][N] (T models)    │
 │   -> model.npz  (a few kB)               │     │ no HotSpot, NumPy only, µs per call  │
 └──────────────────────────────────────────┘     └──────────────────────────────────────┘
```

Calibration may be slow (seconds to minutes) because it runs once. The predictor must be fast
and small because it runs inside a DTM controller or a scheduler, every 1–10 ms.

### 1.2 What "coefficients" are being calibrated

HotSpot is a linear RC network when leakage is off (checked in P0-2). That fixes the shape of
the predictor; calibration finds the numbers for one specific floorplan.

| Part | Coefficients | Physical meaning | Size for N cores/blocks |
|---|---|---|---|
| Steady state | Influence matrix **G** (K/W): `T = T_amb + G·P` | G_ii is how much core i heats itself; G_ij is how much core j heats core i | N² |
| Transient | A few time constants τ_m and weights a_ijm, or a discrete state-space (A, B, C) | How fast each core heats up and cools down, and how heat travels between cores | N²·M (M ≈ 3–5) or r² + 2rN |

**Why heterogeneity matters.** A big core and a little core differ in area, power range and
heat capacity. So they differ in self-heating (G_ii), in coupling to their neighbours, and in
time constants. A generic model with one coefficient per core type cannot capture where each
core sits on the die (edge, corner, next to the GPU). Calibration measures every core
individually. P1-3 shows the gap.

### 1.3 Inputs and outputs

```
Calibrate: ltp.calibrate(flp, config, method)            ->  model.npz
Steady:    ltp.steady(model, P[N])                        ->  T[N]
Transient: ltp.transient(model, T0, P[K][N])              ->  T[K][N]  (open-loop, from start temps)
Forecast:  ltp.forecast(model, T_measured, P_next, k)     ->  T for the next k steps (used by DTM)
```

`transient` answers "what will HotSpot give for this power trace". It needs only the power trace
and a starting condition (cold chip at ambient, or warm chip at the steady state of the first
power row). Every model then feeds its *own* predicted temperatures forward step by step; no
measured temperature is used. This is the core predictor the problem statement asks for.

`forecast` is the run-time version used by DTM (P6). On a real chip, thermal sensors give the
current temperature every interval; in our experiments HotSpot's output stands in for those
sensors. The model restarts from the measured value at each step, so its errors cannot build up.

### 1.4 The three metrics and our targets

These are *targets* taken from the literature, not promises. The report states whether each was
met. On the TA floorplans N = 8 power inputs (2 big + 6 little cores), so G for the cores is
8 × 8 = 64 numbers (512 bytes), or 8 × (8 + FILL blocks) if FILL temperatures are predicted too.
The HotSpot reference is the 64×64 grid model, which is slower than the block model, so the speed
gap should be larger than the old estimate below.

| Metric | Steady predictor | Transient predictor | HotSpot (measured in P0) |
|---|---|---|---|
| **Accuracy**: mean abs. error per block | ≤ 0.1 K | ≤ 0.5 K over the trace | reference |
| Accuracy: error in T_peak | ≤ 0.2 K | ≤ 1 K | |
| Accuracy: hottest core identified correctly | ≥ 99 % | ≥ 95 % | |
| **Prediction time** (median, one CPU thread) | ≤ 20 µs per call | ≤ 50 µs per step | ≈ 10 ms per block steady run; grid 64×64 to be measured (P0-4) |
| **Model size** (bytes in the model file) | ≤ 5 kB | ≤ 50 kB | n/a |
| *Calibration cost* (secondary) | ≤ N+1 HotSpot runs | ≤ 2 min wall time | n/a |

Calibration cost is not one of the three required metrics. We report it anyway because "one-time"
only helps if it is cheap.

---

## 2. Research questions

1. **RQ1, calibration:** what is the cheapest calibration (fewest HotSpot runs, shortest trace)
   that gives accurate coefficients for a heterogeneous floorplan? Is calibrating per floorplan
   actually necessary?
2. **RQ2, steady state:** how accurate, fast and small is the calibrated steady predictor?
3. **RQ3, transient:** how does transient accuracy depend on model order (and so size) and on
   how far ahead we forecast?
4. **RQ4, trade-off:** what is the accuracy / time / size Pareto front across all models?
5. **RQ5, wishlist:** does a forecast from the predictor make DTM *proactive* (acting before the
   limit) and better than reactive DTM?

---

## 3. The models

All models except the baselines are fitted by the calibration stage. Their families come from
the lit review: superposition (§3.1), MatEx and exponential models (§3.2), model-order reduction
(§3.3), power blurring (§3.4), AR/ARX run-time predictors (§4.1, §4.2).

### Steady state

| ID | Model | Calibration needs | Size | Expected |
|---|---|---|---|---|
| S0 | **Uncalibrated baseline**: power blurring with a generic heat-spread kernel (no floorplan-specific fitting) | 1 point-source run, shared by all floorplans | kernel only | 1–3 K error, worst at die edges; shows what calibration buys |
| S1 | **Influence matrix G** | N runs, 1 W in one block each (or N step runs, shared with T3) | N² | Exact without leakage (≪ 0.01 K) |
| S2 | **Compressed G**: one shared "package" term for all cores (every watt warms the common spreader and sink) plus only the k nearest-neighbour couplings per core | same as S1 | ≈ N·(k+1) + 1 | Small accuracy loss; only matters for many cores (e.g. a 64-core floorplan), since G for the TA's N = 8 is just 512 B. Tested on larger floorplans we generate (P3-3) |
| S1-hot-max | **Hot-spot G**: same as S1 for every grid cell inside each core; the output is the hottest of them instead of the core average | same runs as S1, reading the 64×64 grid map | cells × N (compressible, P2-3) | Exact for the chosen cell; addresses the scope risk that block averages hide hot spots (P2-3) |

### Transient

| ID | Model | Calibration needs | Size | Expected |
|---|---|---|---|---|
| T0 | **Persistence**: next T = current T | nothing | 0 | Only good for very short horizons; the minimum to beat |
| T1 | **First-order lag**: each core moves toward its S1 steady value with its own time constant τ_i | S1 runs + N step responses | N² + N | Very small; misses the slow heat-sink tail |
| T2 | **ARX**: next T from the last few *predicted* temperatures and the power (least squares), steady gain fixed to match G | one calibration trace with rich power changes | N²·(n_a + n_b) | Close to exact with 2–3 lags; needs long-enough calibration trace |
| T3 | **Sum of exponentials**: G_ij(t) = Σ_m a_ijm (1 − e^{−t/τ_m}) with M shared τ's. Run as N·M filtered power values, each updated once per step | N step-response runs (same runs as S1) | N²·M + M | Near-exact with M = 3–5; one set of runs gives steady and transient |
| T4 *(opt.)* | **Exact state-space** from HotSpot's own R and C matrices (thousands of nodes in the 64×64 grid model with the TA's layers), then **reduced** by balanced truncation to r ≪ that | small C helper linked to HotSpot | r² + 2rN | Exact at full order; shows how small the model can get. Harder with the grid model, so it stays optional |

**Where do the "past temperatures" come from?** In `transient` (open loop), T2 uses its own
earlier predictions, starting from the initial condition, so the only input is power. In
`forecast` (DTM), it uses sensor readings. T1, T3 and T4 never need past temperatures at all; they
carry an internal state that is computed from the power alone.

**Do the coefficients depend on the workload or the mapping?** No, not in principle. With leakage
off, HotSpot is a fixed linear system set by the floorplan and package. A workload or a mapping
only changes the *input* (how many watts each core gets, and when). Moving a task from core 2 to
core 5 means moving its watts from P_2 to P_5; the coefficients stay the same. Two practical
caveats: (1) a least-squares fit (T2) is only as good as its calibration trace, so that trace
must excite every core independently over short and long time scales, rather than look like one
real workload; (2) leakage makes power depend on temperature (P4-3). P4-1 tests both by checking
models on workloads and mappings unlike the calibration data. (A pure AR model, which uses
temperature only and no power, *is* workload-dependent; that is why it is not in this plan.)

**A trap to plan for:** HotSpot has hidden nodes (FILL blocks, TIM, spreader, sink; with the grid
model, every grid cell) besides the N cores we observe. The sink has a time constant of tens of seconds. A model
that only looks at the N block temperatures with one lag cannot be exact. This is why T2 uses
several lags with the steady gain fixed, T3 uses several time constants, and the calibration
traces must be long enough to show the slow tail.

The final `ltp` ships **S1** for steady state and the best transient model from P3. We expect
T3, since it is near-exact and shares its calibration runs with S1.

---

## 4. Ground truth and data

### 4.1 HotSpot settings and floorplans

- **Reference: HotSpot grid model, 64×64, with each floorplan's `.lcf`** (silicon 150 µm + TIM
  20 µm), run the way the TA README shows. HotSpot accepts a layer file only with the grid model.
  HotSpot still writes one temperature per block (the average over its cells) to `-steady_file`
  and the `.ttrace`; this is what DTM uses and what the predictor outputs. The 64×64 map
  (`-grid_steady_file`) is kept for P2-3.
- Package: example1 config (ambient 45 °C, spreader 30 mm, sink 60 mm, larger than every die)
  with `grid_rows = grid_cols = 64`, because the TA did not include a `hotspot.config` (§10).
  Leakage is off unless stated.
- Transient sampling interval Δt = 1 ms (the DTM interval). The predictor runs at the same Δt. If
  grid-model transient runs turn out too slow for long traces (measured in P0-4), use HotSpot's
  default 10 ms instead and say so.
- The block model on the same floorplans is kept as a cross-check (P0-3).

| Floorplan | What | N inputs | Role |
|---|---|---|---|
| **TA 2D, 23 floorplans** | 2 big (4×4 mm) + 6 little (2×2 mm) cores; Style_1–4; dies 6×10 to 14×14 mm; 29–93 % of the die is cores (`dataset.md` §1.5) | 8 | **Main set.** Every experiment reports results over all 23, grouped by style |
| *Main subset* | Style_1 fp_001, Style_2 fp_004, Style_3 fp_002, Style_4 fp_001 (one per style) | 8 | For the expensive experiments (long transient traces, P3-3, P6) and for the figures |
| *Style_4 group* | 10 floorplans with the same 14×14 mm die; only core positions differ | 8 | Transfer and "per-core-type" tests in P1-3 |
| **HET-A** | Ours (branch `p0-flpgen`): 2 big, 4 little, shared L2, NoC | 8 | Keeps the "shared cache" promised in the scope; non-core blocks with their own power |
| **EV6** | Stock Alpha 21264 from example1 | 30 | Sanity check; the only real trace (gcc) |
| **Generated, TA styles** | `flpgen.py` copies the TA's Style_1–4 recipes with the same 8 cores, about 10 per style (the README calls the samples "templates for generating more data") | 8 | More layouts for P1-3(d) and P2-2; reported separately from the 23 given ones |
| **Generated, larger** | `flpgen.py` in the TA's styles: 16 and 32 cores, other die sizes, optionally a third core type | 16–32 | Stretch only: model-size story for S2 (P3-3) and robustness (P4-1) |

The TA's 3D floorplans are not used (TA advice; outside our scope).

### 4.2 Power

Power ranges come from the TA README: **big 10–20 W, little 5–10 W**. Power is always assigned by
core *size* (4×4 mm = big, 2×2 mm = little), never copied from the TA's `.ptrace` files, because
four Style_2 files give the big-core power to little cores (`dataset.md` §1.7). Little cores have
the higher power density (up to 2.5 W/mm² against 1.25 W/mm² for big cores), so a little core can
be the hottest one. FILL blocks are always 0 W. On HET-A, L2 and NoC get 1–4 W.

- **Calibration inputs:** a 1 W (or 10 W, see P0-4) step in one core at a time (S1, T1, T3); one
  long excitation trace where each core randomly switches between levels in its range, with mixed
  phase lengths from 1 ms to several seconds (T2).
- **Test inputs (never used in calibration):**
  - *Steady:* the TA's nominal vector (big 20 W, little 8 W), plus 1,000 random vectors per
    floorplan within the ranges.
  - *Transient:* phase-based workload traces in the TA's `.ptrace` format, with other random seeds.
    Each core follows its own sequence of phases (idle at the bottom of its range, busy at the top,
    and DVFS levels in between), plus a few bursty traces and task migrations between cores. The
    TA's own transient ptraces cannot be used as tests because all 200 rows are the same.
  - gcc.ptrace for EV6.

---

## 5. Experiments

**Difficulty:** ★ easy (run HotSpot, a short script, a plot). ★★ medium (new code or a model to
fit, some debugging). ★★★ hard (a technique you'd need to learn first, or C-level work).
**[CORE]** = needed. **[OPT]** = only if time allows. **[WISH]** = the wishlist item.

### Summary

**Owner:** E or K (see §12 for the reasoning behind the split). Every experiment is explained
for beginners, with the concepts it needs, in `hotspot_for_dummies.md` Part B.

| ID | Experiment | Stage | Type | Difficulty | Owner |
|---|---|---|---|---|---|
| J0 | Agree on shared interfaces (file formats, model API) | setup | CORE | ★ | E + K |
| P0-1 | Example1 reproduced | ground truth | CORE | ★ (done) | E |
| P0-2 | Linearity checks | ground truth | CORE | ★ | E |
| P0-3 | Block vs grid model, and grid resolution | ground truth | CORE | ★ | K |
| P0-4a | Infrastructure: run HotSpot, parse, parallel sweep | ground truth | CORE | ★★ | E |
| P0-4b | Infrastructure: floorplan and power generators | ground truth | CORE | ★ | K |
| P0-5 | Load the TA floorplans; power and trace generators; check temperatures | ground truth | CORE | ★ | K |
| P1-1 | Calibration by impulse/step runs (S1, T1, T3) | calibration | CORE | ★★ | E |
| P1-2 | Calibration from one trace (T2), and how long it must be | calibration | CORE | ★★ | K |
| P1-3 | Is per-floorplan calibration needed? (includes building S0) | calibration | CORE | ★★ | K |
| P2-1 | Steady predictor: S0, S1, S2 | predictor | CORE | ★ | E |
| P2-2 | Layout effects across the 23 floorplans | predictor | CORE | ★ | K |
| P2-3 | Hot spots inside cores (S1-hot) | predictor | CORE | ★ | E |
| P3-1 | Transient simulation: T1, T2, T3 | predictor | CORE | ★★ | E |
| P3-2 | Forecasting: error vs horizon | predictor | CORE | ★ | K |
| P3-3 | Accuracy vs size vs time (Pareto) | predictor | CORE | ★★ | K |
| P3-4 | Exact state-space and balanced truncation (T4) | predictor | OPT | ★★★ | E |
| P4-1 | Robustness: power outside calibration range, other workloads and mappings | both | CORE | ★ | E |
| P4-2 | Recalibration after a package change | calibration | OPT | ★ | K |
| P4-3 | Leakage (nonlinear power) | both | OPT | ★★ | E |
| P5-1a | `ltp` package skeleton; `calibrate`, `steady`, `transient`, `forecast` commands | product | CORE | ★ | E |
| P5-1b | `ltp bench` (the three metrics) and tests | product | CORE | ★ | K |
| P6-1 | Closed-loop HotSpot for DTM | DTM | WISH | ★★ | E |
| P6-2 | Reactive vs proactive DTM | DTM | WISH | ★★ | K |
| P6-3 | Demo: which cores to switch on | DTM | WISH | ★ | E |

### Phase P0: Ground truth you can trust

**P0-1 [CORE] ★ Example1 reproduced and understood.** *Done* (see `README_SETUP.md`).

**P0-2 [CORE] ★ Linearity checks.**
Scale all power by 0.5×, 2× and 3×; run two power patterns separately and together; zero power.
*Expect:* temperature rise scales exactly, patterns add up, zero power gives ambient.
*Why it matters:* this is what makes S1, T2 and T3 work. If it holds, any later error in them is
a bug or a calibration problem, not physics.

**P0-3 [CORE] ★ Block vs grid model, and grid resolution.**
On the main subset (one floorplan per style), run the block model and the grid model at 32, 64
and 128 with the TA's nominal power.
*Output:* (a) how much the block model and the 64×64 grid model differ per core; (b) whether 64×64
is fine enough (change from 64 to 128); (c) how much hotter the hottest cell inside each core is
than its average; (d) HotSpot's runtime for each. (c) sets the size of the problem P2-3 solves.

**P0-4 [CORE] ★★ Infrastructure.** Python scripts to run HotSpot and save everything
(`run_hotspot.py`), read its outputs (`parse.py`), write floorplans (`flpgen.py`) and power traces
(`powergen.py`), and run many simulations in parallel with resume (`sweep.py`). Also time one
HotSpot steady run and one transient step, to fill the HotSpot column in §1.4.
**Precision fix (E):** HotSpot prints temperatures with only 2 decimals (`%.2f`, i.e. 0.01 K
steps) in `.steady` and `.ttrace`. That rounding would swamp "≪ 0.01 K" errors and add noise to
every fit. Keep a small patch file (`patches/precision.patch`, `%.2f` → `%.6f` in `dump_temp` in
`temperature_block.c`, `write_vals` in `hotspot.c`, and the grid dump functions) that both of us apply after building the submodule. As a cross-check, also run
calibration with 10 W steps instead of 1 W, which makes the rounding relatively 10× smaller.

**P0-5 [CORE] ★ TA floorplans, power and traces.**
(a) A loader that reads a TA floorplan folder (`.flp`, `.lcf`, `_tim.flp`) and tags each core as
big or little by size. (b) `powergen.py`: random steady vectors and phase-based transient traces
within the TA ranges, written in the TA's `.ptrace` format (all block columns, FILL = 0 W).
(c) Run all 23 floorplans at the TA's nominal power and at all-cores-maximum power.
*Output:* a table of peak temperature and hottest core per floorplan. Check that temperatures are
plausible (roughly 60–110 °C); if the example1 package makes them far too hot, raise it with the
TA rather than change their power ranges. Note whether the hottest core is big or little.
HET-A from `flpgen.py` (branch `p0-flpgen`) is the extra floorplan with a shared L2.
(d) Extend `flpgen.py` to generate new floorplans in each TA style (`dataset.md` §1.9), writing
`.flp`, `_tim.flp` and `.lcf` in the TA's format, about 10 per style.

### Phase P1: Calibration stage

Cases: all 23 TA floorplans, HET-A, EV6. Calibration is cheap here: 8 step runs per TA floorplan,
184 runs for all 23.

**P1-1 [CORE] ★★ Calibration by impulse/step runs.**
For each core, run HotSpot with a step in that core alone (FILL blocks need no runs, they are
always 0 W), long enough to reach steady state. The final values give **G** (S1); the grid maps
of the same runs give S1-hot. The curves give the time constants τ_i (T1) and the exponential
weights a_ijm with shared τ_m (T3, fitted by least squares).
*Output:* calibrated model files for all floorplans; a heat map of G that shows the big/little
differences; calibration cost (runs, seconds); fit error on the calibration runs themselves.

**P1-2 [CORE] ★★ Calibration from one trace.**
Fit ARX (T2) by least squares on one excitation trace, with the steady gain fixed to G.
Repeat with traces of 1, 5, 20 and 60 s.
*Output:* **test error vs calibration trace length.** This shows the cheapest calibration that
still works and makes the slow heat-sink tail visible.

**P1-3 [CORE] ★★ Is per-floorplan calibration needed?**
The TA data is ideal for this: all 23 floorplans have the same 8 cores and the same power, and the
10 Style_4 floorplans even share the same die. Only the layout differs. Compare S1 with:
(a) uncalibrated S0 (power blurring), on all 23;
(b) a "per core type" model: one self-heating value and one coupling-vs-distance curve for big
cores and one for little cores, fitted on the other floorplans and applied to this one;
(c) transfer: use one Style_4 floorplan's G on the other nine (same die, same cores, cores
matched by type and index), and the same across styles;
(d) a leave-one-floorplan-out regression: predict each G_ij from simple geometry (core sizes,
distance between cores, distance to the die edge, die size, white space), trained on the other 22
floorplans. This is the strongest calibration-free baseline we can build from the data.
*Output:* one table: steady error on the test vectors for S1 vs (a)–(d), per style.
*Expect:* (a)–(d) are all clearly worse than S1, and (d) is the closest. This justifies the
one-time calibration and shows that position on the die matters, not only core type.

### Phase P2: Predictor, steady state

**P2-1 [CORE] ★ Steady predictor (S0, S1, S2).**
Test on the TA's nominal vector and 1,000 random power vectors per floorplan (within the TA
ranges), for all 23 floorplans, and on gcc's average power for EV6.
*Expect:* S1 error ≈ 0 (≪ 0.01 K) in a few microseconds; S2 trades a little accuracy for size.
*Output:* table with the three metrics (error, µs per prediction, bytes) against HotSpot's
time for the same inputs, summarised per style (mean and worst floorplan).

**P2-2 [CORE] ★ Layout effects across the 23 floorplans.** No new runs: it reads the calibrated G
of every floorplan. Plot self-heating G_ii against core type and distance to the die edge, and
coupling G_ij against distance between cores. Plot peak temperature at nominal power against die
size and white space (29–93 % cores).
*Output:* two or three figures that explain *why* coefficients differ between floorplans (the
"why" behind P1-3), and a check of the TA's remark that white space keeps the chip cooler.

**P2-3 [CORE] ★ Hot spots inside cores (S1-hot).** From the grid maps of the P1-1 runs, pick the
hottest cell of each core at nominal power and calibrate G for those cells. Test like P2-1, with
the true per-core maximum from the grid map as the reference.
*Output:* error of "core average" and of S1-hot against the true hottest cell. This answers the
scope risk "block-level model may hide hot spots inside large cores" with data. The hottest cell
can move a little when the power pattern changes, so the error is small but not zero.

### Phase P3: Predictor, transient

**P3-1 [CORE] ★★ Transient simulation (T1, T2, T3).**
Given the start temperatures and a whole test power trace, predict the whole temperature trace
(open loop) and compare with HotSpot. Test traces have unseen seeds, plus gcc on EV6. Long traces
on the main subset; short traces (a few hundred steps) on all 23 floorplans.
*Output:* error over time for each model; the three metrics per model.

**P3-2 [CORE] ★ Forecasting: error vs horizon.**
Restart from HotSpot's temperatures at each step and forecast 1, 10, 100 and 1,000 ms ahead,
using the planned power for those steps. Include persistence (T0).
*Output:* **error vs forecast horizon** plot. This is the curve DTM depends on in P6.

**P3-3 [CORE] ★★ Accuracy vs size vs time.**
Vary the size of each model: M for T3, the number of lags for T2, k for S2, and r for T4 if done.
With only 8 cores every model is small, so S2 is also run on generated 16- and 32-core floorplans
in the TA's style (stretch goal "model-size reduction for larger core counts").
*Output:* **the Pareto plot** (error against model size, coloured by prediction time). This is
the main figure of the report, because it shows all three required metrics at once.

**P3-4 [OPT] ★★★ Exact state-space and balanced truncation (T4).**
A small C helper, built against `libhotspot.a`, exports HotSpot's internal R and C matrices.
Turn them into a discrete-time state-space model at Δt, then shrink it with balanced truncation.
*Output:* the exact reference point and the smallest accurate order r. Only worth it if T2 and
T3 are clearly off in P3-1.

### Phase P4: Robustness of the calibrated predictor

**P4-1 [CORE] ★ Where does it break?** No new models, only new test inputs: power above the
calibration range, very bursty workloads, different task mappings (the same tasks moved to other
cores, including big → little), a different Δt. *Expect:* S1/T3 are unaffected because the system
is linear; T2 may degrade on inputs unlike its calibration trace.

**P4-2 [OPT] ★ Recalibration after a package change.** Change the heat sink (`r_convec`) and the
ambient temperature, as IC-ThermBench does (`dataset.md` §2). Show that an ambient change needs no
recalibration (it only moves T_amb), that a heat-sink change makes the old coefficients fail, and
that recalibration costs only the P1-1 runs.

**P4-3 [OPT] ★★ Leakage.** Turn on HotSpot's temperature-dependent leakage, so the system is no
longer linear. Measure how much S1 and T3 degrade, then add a small fixed-point correction
(recompute leakage power from the predicted T, predict again). Links to Prof. Kedia's work
(lit review §6.2).

### Phase P5: The product

**P5-1 [CORE] ★★ Package `ltp`.** Commands `ltp calibrate`, `ltp steady`, `ltp transient`,
`ltp forecast`; models saved as `.npz`; `ltp bench`, which prints accuracy, prediction time and
model size against stored HotSpot outputs; a few tests; a short README.

### Phase P6: Wishlist, proactive DTM

**P6-1 [WISH] ★★ Closed-loop HotSpot.** DTM needs a "chip" whose power can change every interval
in response to its temperature. HotSpot's transient mode reads a fixed trace, and its outputs keep
only block temperatures (package node temperatures are lost between runs). So we build a small
stepper on HotSpot's library interface (`sim-template.c` in the HotSpot source shows how): call
`compute_temp` once per 1 ms interval with the power the DTM policy chose. The stepper is the
plant; `ltp` is the predictor in the controller.

**P6-2 [WISH] ★★ Reactive vs proactive DTM on the main subset** (one TA floorplan per style).
Temperature limit e.g. 85 °C. Power levels per core type come from the TA ranges (big 10–20 W,
little 5–10 W). Note that little cores have the higher power density, so moving a task to a little
core does not always cool the chip; the predictor is what tells the policy whether it will.
- *Reactive:* throttle (lower DVFS level) a core once it is *already* above the limit.
- *Proactive:* every 10 ms, use `ltp.forecast` to predict k steps ahead. Throttle, or move the
  task from a big core to a cool little core, *before* the limit would be crossed.
- Also compare proactive DTM using a perfect predictor (HotSpot itself) and a poor one
  (persistence), to show that predictor accuracy is what matters.
*Metrics:* peak temperature, time above the limit, number of violations, performance lost
(sum of frequency over time, as a proxy), and predictor time per DTM decision.
*Expect:* proactive DTM has fewer violations and less performance loss than reactive DTM.

**P6-3 [WISH] ★ Demo: which cores to switch on.** On a Style_4 floorplan, choose which cores run a
set of busy tasks. Score every choice with `ltp.steady` (S1) and with HotSpot.
*Report:* is the coolest choice the same, and how long does each take? Easy, and it shows the
steady predictor being used for a decision.

---

## 6. Evaluation rules

- **Accuracy:** mean and max absolute error (K) per block, T_peak error, hottest-core accuracy.
  For transient: error over the whole trace, and error vs forecast horizon.
- **Prediction time:** median over ≥ 10,000 calls after warm-up, single CPU thread, Python
  overhead included. HotSpot is timed on the same inputs, with and without process start-up.
- **Model size:** number of coefficients and bytes in the saved model file (float64; also
  float32 if accuracy allows).
- **Calibration cost:** number of HotSpot runs and wall time, reported separately.
- **Baselines always shown:** S0 (uncalibrated) for steady state, T0 (persistence) for transient.
- **Calibration and test inputs never overlap.** Test sets are used once, at the end.
- **Across floorplans:** report each metric per floorplan, then mean and worst case per style and
  over all 23. One floorplan picked by hand is not a result.

---

## 7. Repository layout

```
Lightweight Thermal Predictor/
├── hotspot_for_dummies.md, plan.md, dataset.md, README_SETUP.md
├── setup/          build_hotspot_ltp.sh + ltp.patch: patched HotSpot (6-decimal output, LU caching)
├── configs/        HotSpot configs (base grid 64×64, base block)
├── data/sample_dataset/  the TA's dataset, as committed on branch p0-flpgen (read-only)
├── floorplans/     het_a, hom_16 (flpgen.py); stacks/ = generated TA-style .lcf files
├── src/sim/        floorplans.py (loader), hotspot.py (runner + parser), gridmap.py,
│                   powergen.py, datasets.py (cached test sets), parallel.py, flpgen.py
├── src/ltp/        the product: models.py (S1, T1, T2, T3), calibrate.py; later CLI, bench
├── experiments/<ID>_<name>/   one folder per experiment: run.py, README.md (findings),
│                   results/ (CSVs, figures, log.txt); run with  bash experiments/run.sh <ID>_<name>
└── PROGRESS.md     short dated log of what each of us did and found
~/ltp_runs/ (inside WSL, not in git): every HotSpot run, the calibration cache (calib/) and
                    test sets (datasets/), all regenerated from seeds by the experiment scripts
```

Simulations run in WSL Ubuntu; the code is read from the Windows checkout (`/mnt/c/...`) and all
HotSpot files go to `~/ltp_runs` on the Linux file system. Tools: NumPy/SciPy, matplotlib. No
deep-learning libraries are needed.

---

## 8. Order of work

| Step | E works on | K works on | Deliverable |
|---|---|---|---|
| 1 | J0, P0-4a, P0-2 | J0, P0-4b, P0-5, P0-3 | Trusted ground truth, heterogeneous floorplans, scripts |
| 2 | P1-1, P2-1, P2-3 | S0 kernel, P1-3, P2-2, start P1-2 | Calibrated steady predictor with all three metrics, on all 23 floorplans |
| 3 | P3-1, P5-1a | P1-2, P3-2 | Calibrated transient predictor; why per-floorplan calibration is needed |
| 4 | P4-1, P6-1 | P3-3, P5-1b | Pareto plot; robustness table; `ltp` usable from the command line |
| 5 | P6-3, then [OPT] items | P6-2 | Proactive DTM result |
| 6 | Report: calibration and steady chapters | Report: transient and DTM chapters | Write-up and slides (both) |

**Minimum viable project** (if time is short): P0, P1-1, P1-3, P2-1, P3-1, P3-2, P3-3, P5-1.
P2-2 and P2-3 cost no new HotSpot runs, so they should fit even then.
That gives both stages, steady and transient prediction, and all three metrics. Next in priority
is P6-2 (the wishlist), then P1-2, then the [OPT] items.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| HotSpot rounds output to 0.01 K | Precision patch (P0-4a) and 10 W calibration steps |
| ~~No given floorplan~~ | Resolved: the TA dataset gives 23 heterogeneous 2D floorplans |
| No `hotspot.config` from the TA | Use example1 with a 64×64 grid; ask the TA for theirs and rerun if it differs (calibration is cheap) |
| TA transient traces are constant; no real workload power beyond gcc | Generate phase-based traces within the TA ranges; the TA suggests turbostat/RAPL for real power later |
| Style_2 ptraces give big-core power to little cores | Assign power by core size ourselves; tell the TA |
| Only 8 cores, so model size is never an issue on the TA data | Show S2 on generated 16/32-core floorplans |
| Grid model is slower than the block model | Time it in P0-4; long transient traces only on the main subset; fall back to Δt = 10 ms if needed |
| Block model hides hot spots inside big cores | P0-3 measures the size of the effect; P2-3 calibrates the hottest cell per core |
| Slow heat-sink time constant makes calibration traces long | Fix the steady gain to G; use step runs (T3), which reach steady state anyway |
| Closed-loop DTM needs C work against HotSpot | It is the wishlist, last in order; `sim-template.c` is a ready starting point |
| HotSpot is not real silicon | Say so plainly: we predict *HotSpot*, which is itself within about 1–2 °C of detailed tools |

---

## 10. Decisions needed

1. ~~Will the professor provide the floorplan(s)?~~ Done: TA dataset, 23 2D floorplans.
2. Ask the TA: which `hotspot.config` (package, ambient, `sampling_intvl`) did they use, and are
   the Style_2 power assignments intended?
3. Is synthetic power within the TA ranges acceptable for the transient tests? (The TA README
   suggests yes.)
4. How far should the DTM wishlist go: DVFS throttling only, or also big→little task migration?
5. Deadline, to decide which [OPT] items stay.

---

## 11. Out of scope (moved from the earlier plan)

The earlier plan had a second "design-time" mode: one learned predictor that works on floorplans
it has never seen, without calibration (gradient boosting on block features, and a small CNN
trained on ~1,500 random floorplans; lit review §5). The problem statement asks for calibration
*per given floorplan*, so this is no longer part of the plan. What we keep from it: power blurring
as the uncalibrated baseline S0, the small geometry regression in P1-3(d) as a baseline (not a
product), and the floorplan generator, if a stretch goal is ever wanted.

Also out of scope: the TA's 3D floorplans (TA advice), and training on IC-ThermBench or
ATPlace2.5D data (2.5D chiplets, steady state, no fixed floorplan under many power inputs; see
`dataset.md` §2–3). IC-ThermBench is used only as a published comparison point for accuracy and
model size of learned surrogates.

---

## 12. Division of work: E and K

**The idea of the split.** E owns the **step-response line** (S1, T1, T3, and T4 if time allows)
and the **HotSpot plumbing** (runner, closed-loop stepper). K owns the **trace-fitting and
baseline line** (T2, S0), the **forecasting and comparison** experiments, and the **DTM
policies**. Each of us owns models end to end, from calibration to evaluation, so each of us has
a full story to present. The work is about equal: both lines add up to roughly 13 stars of CORE
and WISH work, and each has one or two [OPT] items.

| | E | K |
|---|---|---|
| Ground truth | P0-2 linearity, P0-4a runner/parser/sweep | P0-3 block vs grid, P0-4b generators, P0-5 TA floorplans and power |
| Calibration | P1-1 step-response calibration | P1-2 trace calibration (ARX), P1-3 is calibration needed (S0) |
| Predictor | P2-1 steady, P2-3 hot spots, P3-1 transient | P2-2 layout effects, P3-2 forecast horizon, P3-3 Pareto plot |
| Robustness | P4-1; [OPT] P4-3 leakage | [OPT] P4-2 recalibration |
| Product | P5-1a package and commands | P5-1b `ltp bench` and tests |
| DTM (wishlist) | P6-1 closed-loop HotSpot, P6-3 demo | P6-2 reactive vs proactive DTM |
| [OPT] hard item | P3-4 exact state-space (C) | n/a |

**Hand-offs**, and how to avoid waiting on each other:

| Waiting for | From | Until it arrives |
|---|---|---|
| `run_hotspot.py`, `sweep.py` (P0-4a) | E → K | K writes floorplans and runs P0-3 with plain HotSpot shell commands |
| TA floorplan loader and power generator (P0-5) | K → E | E develops P1-1 on one TA floorplan read by hand, or on EV6 |
| T2 model (P1-2) | K → E | P3-1 evaluates whatever models exist; T2 is added when ready |
| All models (P1, P3-1) | both → K | K builds P3-3's plotting from `results/summary.csv` with early rows |
| HotSpot stepper (P6-1) | E → K | K writes DTM policies against T3 as a stand-in chip, then swaps in the stepper |

**J0 (first meeting, both).** Fix the interfaces before anyone writes models, so parts plug
together:
1. Every model is a Python class with `calibrate(...)`, `steady(P)`, `transient(T0, P_trace)`
   and `forecast(T_now, P_next, k)`. A model can raise `NotImplementedError` for what it does not
   support (for example, S0 has no transient).
2. Model file: `.npz` with a `kind` field, the floorplan name, the block order, Δt and the
   coefficients.
3. One HotSpot run on disk is `data/runs/<floorplan>/<run_id>/` with the `.ptrace`, the `.ttrace`
   and/or `.steady` output, the grid map if any, and `meta.json` (config, seed, git commit,
   HotSpot commit). Floorplan names follow the TA's folders, e.g. `s4_fp_003`.
4. `results/summary.csv` columns: `model, floorplan, test_set, mae_K, max_K, peak_err_K,
   hottest_acc, time_us, size_bytes, calib_runs, calib_s, git_commit, who, date`.

---

## 13. How we work together (two Windows + WSL laptops)

**Yes, GitHub is enough.** Use it as follows.

**Setup, once each:**
- Clone the repo **inside WSL** (e.g. `~/projects/ltp`), not under `C:\`. File access is much
  faster there, and line endings stay Linux-style. Open it from VS Code with the *WSL* extension
  (`code .` from the Ubuntu terminal).
- Add K as a collaborator on `ethnn-b/lightweight-thermal-predictor`.
- The repo already forces LF line endings (`.gitattributes`), so CRLF problems with scripts
  won't come back.
- Use the same HotSpot: the submodule pins a commit (currently `f18831e`). Both run
  `git submodule update --init` and `make SUPERLU=1` as in `README_SETUP.md`. Also add a
  `requirements.txt` with pinned versions and one Python venv each.

**Day to day:**
- **One branch per experiment**, named `e/p1-1-step-calibration`, `k/p1-2-arx`. Merge into `main`
  through a pull request that the other person at least skims. This is how each of us learns
  what the other did, which matters at the final viva.
- **Commit code, configs and small results; never raw runs.** `data/runs/` is git-ignored (the
  TA dataset in `data/sample_dataset/` is small and stays committed). Every run
  is regenerated by `sweep.py` from fixed seeds, so commit the seed, not the output. If a big
  dataset must be shared, zip it and attach it to a GitHub Release (or put it on Drive) and note
  the link in the experiment's README.
- **Every result records its origin**: `meta.json` and `summary.csv` rows include the git commit,
  so any number can be traced to the code that produced it.

**Tracking progress:**
- **GitHub Issues, one per experiment** (P0-2, P1-1, ...), labelled `E` or `K`, `CORE`/`OPT`/`WISH`,
  and a **GitHub Projects board** with columns *To do / In progress / In review / Done*. A glance
  at the board shows how far we have got. Milestones = the six steps of §8.
- **Each experiment ends with `results/<exp>/README.md`**, about half a page: question, command to
  reproduce, headline numbers, one or two figures, conclusion, open questions. Closing the issue
  links this README. These pages become the report chapters almost directly.
- **`results/summary.csv`** collects the three metrics for every model in one table, so neither of
  us has to ask "what was your error again?".
- **`PROGRESS.md`**: a dated line or two per work session (`2026-10-20 K: HET-A written, peak
  97 °C at full load, too hot, lowering big-core max to 6 W`). Cheap, and it makes weekly
  updates to the professor easy.
- **Two short syncs a week** (15 min, call or chat): walk the board, unblock hand-offs, agree on
  what goes to the professor.

**One rule that matters for the results:** *prediction time* depends on the laptop. All
**final** timing numbers (HotSpot and every model) must be measured on **one** machine, in one
session, with `ltp bench`. Accuracy and model size can come from either laptop.

---

## 14. What changed in the 30 Oct revision, and why

All changes stay inside `Scope_Document.pdf`: the same two stages, the same models, the same
three metrics, the same stretch goals. The data only makes the experiments more convincing.

| Change | Why | Scope item it serves |
|---|---|---|
| TA's 23 2D floorplans are the main set (replacing HET-B, HOM-16); HET-A and EV6 stay | Real, given floorplans instead of our own; results over 23 layouts, not 2 | Ground truth; "calibration per given floorplan" |
| Reference is HotSpot grid 64×64 with the TA's `.lcf` | That is how the TA runs HotSpot; HotSpot only takes a layer file with the grid model | Ground truth |
| Power ranges: big 10–20 W, little 5–10 W, assigned by core size | TA ranges; four Style_2 ptraces have big and little swapped | "Realistic per-core-type power ranges" |
| We still generate transient traces | The TA transient ptraces are constant | Transient predictor |
| P0-3 also checks grid resolution (32/64/128) | 64×64 is the TA's choice; we should know it is fine enough | Ground truth |
| P0-5(d) generates about 10 more floorplans per TA style | README: the samples are "templates for generating more data"; TA asks us to expand the data | Ground truth; strengthens P1-3 and P2-2 |
| P1-3 adds a Style_4 transfer test and a leave-one-floorplan-out regression baseline | The data has the same cores in many layouts, the cleanest test of whether calibration is needed | "Check that per-floorplan calibration is actually needed" |
| New P2-2: layout effects (no new runs) | Explains *why* coefficients differ between floorplans; tests the TA's white-space remark | Evaluation |
| New P2-3: hottest cell per core (S1-hot, no new runs) | The grid model gives the maps for free | Scope risk "block-level model may hide hot spots" |
| S2 on generated 16/32-core floorplans | With 8 cores, model size is never a problem on the TA data | Stretch goal "model-size reduction for larger core counts" |
| P4-2 also changes ambient | IC-ThermBench varies ambient and convection; shows ambient needs no recalibration | Robustness |
| IC-ThermBench is a comparison point, not training data | 2.5D, steady state, no fixed floorplan under many power inputs | Evaluation (context for accuracy and size) |
| 3D floorplans not used | TA advice | n/a |

---

## 15. Status (30 Oct 2026)

All experiments of P0–P6 have been run, including the [OPT] and [WISH] items. Each has its own
folder with code, results and a README; the index with one-line results is
`experiments/README.md`, and the dated log is `PROGRESS.md`.

Where the work differs from this plan, and why:

| item | plan | what was done | why |
|---|---|---|---|
| HotSpot build | precision patch | precision patch + LU caching (29× faster transients, identical output) + a fix for a memory leak in HotSpot's grid transient | long transient traces were impractical (4 h) or crashed (out of memory) |
| P0-5(d) | generate more floorplans | 40 generated in the TA styles (`src/sim/tagen.py`) | as planned; used as extra training data in P1-3 |
| P1-3 | (a)–(d) | plus (d2) with generated floorplans and (d3) S0 + learned correction | to give the calibration-free side its best chance |
| S2 | one shared package term | one package term *per output* (mean of the dropped couplings), plus a low-rank variant for comparison | one global term was up to 17 K off on HOM-64 |
| P2-3 | one hottest cell per core | S1-hot-max: max over every grid cell inside each core, plus compression of that matrix | the hot spot moves with the power pattern |
| T4 | balanced truncation of HotSpot's matrices | modal truncation → balanced truncation → fast-part filter | without the filter the error stalled at 3 K |
| P6-1 | C stepper on HotSpot's library interface | HotSpot's own transient driven through pipes | simpler, same binary, verified identical |
| P6-2 | DVFS and/or migration | DVFS only, two limits per floorplan | migration left as a next step |
| Timing | one machine, `ltp bench` | all on Ethan's laptop (WSL, 20 threads); some runs shared the machine with HotSpot jobs (noted in the READMEs) | final numbers should be re-measured on an idle machine |
