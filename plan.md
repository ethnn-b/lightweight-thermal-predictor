# Project plan: How does a floorplan determine chip temperature?

**Working title:** *Lightweight Thermal Predictor: floorplan-driven temperature analysis with
HotSpot, and a fast surrogate model*

**One-line pitch:** Generate many chip floorplans (real and synthetic), simulate each with
HotSpot to find where and how hot the chip gets, work out *which floorplan decisions matter
most*, and finally build a lightweight predictor that estimates temperature without running
the simulator.

Read `hotspot_for_dummies.md` first if any term here is unfamiliar. `lit_review.md` explains
where each experiment comes from.

---

## 0. Can Claude run all of this automatically?

**Mostly yes.** From this VS Code session I can run any command inside your Ubuntu (WSL)
using `wsl -d Ubuntu -- ...`. I already used this to install packages, build HotSpot, and run
examples 1, 2, 3, 5 and 6. So I can write the scripts, run the experiments (in the background
for long sweeps), collect results, make plots, and write up findings.

What **you** must do:

| Step | Why I can't do it |
|---|---|
| Review and approve `plan.md` (choose which optional experiments to keep) | It's your project and your grade |
| Keep the session and PC on during long runs | WSL stops if Windows sleeps or the session ends. The longest planned runs are about 1–2 h |
| Approve tool permission prompts when they appear | VS Code asks before some commands |
| Read the scripts and results until you understand every step (the course requires it) | I'll explain each script, and the "what you learn" lines below are a checklist |
| Ask your professor: is synthetic power data acceptable, or do they expect McPAT/CoMeT-generated power? | Only they can answer (see Risks) |
| Give any course-specific constraints: deadline, team size, report format | I don't know them |

What you do **not** need to do: install anything else, type commands, or paste into the
Ubuntu terminal. If you want to run something yourself, every experiment will be one command
(see §2).

---

## 1. Research questions

1. **RQ1, model fidelity:** how much do HotSpot's own modelling choices (block vs grid,
   resolution, package parameters) change the answer?
2. **RQ2, floorplan → temperature:** for a fixed total power, which floorplan properties
   control the *peak* temperature and the *gradient* across the die? Candidates: power
   density, hot-block placement (centre/edge/corner), clustering vs spreading, aspect ratio.
3. **RQ3, optimisation:** how much peak temperature can thermal-aware floorplanning save,
   and what does it cost in area and wire length?
4. **RQ4, 3D and 2.5D (linked to Prof. Kedia's work):** in stacked and chiplet designs,
   how do layer order and spacing change the hot spot?
5. **RQ5, lightweight prediction:** can a cheap model predict HotSpot's output, how
   accurately, how fast, and does it generalise to *new* floorplans?

---

## 2. Infrastructure (built first, used by every experiment)

```
Lightweight Thermal Predictor/          (Windows; git repo)
├── hotspot_for_dummies.md, lit_review.md, plan.md
├── configs/          base HotSpot config + materials, versioned
├── floorplans/       hand-written (ev6 variants) and generated .flp files
├── power/            .ptrace files (gcc example + synthetic)
├── src/
│   ├── run_hotspot.py     one function: run(flp, ptrace, config, options) -> results folder
│   ├── flpgen.py          synthetic floorplan generator (grid of cores, random slicing, chiplets)
│   ├── powergen.py        synthetic power traces (constant, step, random, per-workload)
│   ├── parse.py           .steady / .ttrace / grid files -> pandas
│   ├── plots.py           heat maps, bar charts, Pareto plots
│   └── sweep.py           runs a parameter grid in parallel, writes results.csv
├── experiments/      one script per experiment (A1.py, B1.py, ...): the exact recipe
└── results/<exp_id>/ raw outputs, results.csv, figures, the exact command lines used
```

Principles:
- **Every run is reproducible.** The results folder stores the inputs, the config, the exact
  HotSpot command and the HotSpot version.
- **One command per experiment**, for example `python3 experiments/C1.py`.
- **Simulations run on the Linux side** (`~/projects/...`) for speed. Results are copied back
  to the Windows folder for reading.
- **Units:** inputs in SI (metres, watts). Report in °C and mm.

Measured costs on this machine (single run, from earlier tests):

| Run type | Time |
|---|---|
| Block model, steady state, EV6 | about 0.01 s |
| Grid 64×64 steady state | about 1 s |
| Grid 128×128 steady state (iterative solver) | about 4 s |
| 3D two-die stack, transient, 64×64 (example3) | about 3 min |
| HotFloorplan on EV6 (example6) | about 90 s |

So a sweep of a few thousand block or 64×64 grid runs takes minutes to an hour, which is fine.

Metrics used throughout:
- **T_peak**: hottest block or grid cell (°C). The usual thermal limit is about 85–100 °C.
- **T_avg**: area-weighted average die temperature.
- **ΔT_grad**: T_peak − T_min across the die (a reliability concern).
- **Hot-spot location**: which block or cell is hottest.
- For transients: **time above threshold**, and **thermal time constant**.

---

## 3. Experiments

Each experiment lists the question, the setup, what we expect, cost, and what you learn.
**[CORE]** = recommended minimum for a solid project. **[OPT]** = pick based on time and
interest.

### Phase A: Setup and sanity checks

**A1 [CORE] Reproduce example1 and understand every file.** *Mostly done.*
Re-run EV6 + gcc, confirm IntReg is the hot spot (about 70 °C steady state), and walk through
`.flp`, `.ptrace`, `.config`, `.steady` and `.ttrace` line by line.
*Learn:* the HotSpot inputs and outputs and the full pipeline.

**A2 [CORE] Physics sanity checks.**
1. *Linearity:* scale all power by 0.5×, 2× and 3×. Without leakage the temperature *rise*
   above ambient should scale exactly. Verify.
2. *Energy balance:* heat-sink temperature rise ≈ total power × `r_convec`
   (40 W × 0.1 K/W ≈ 4 °C, plus a little for spreading).
3. *Zero power* gives ambient everywhere.

*Expect:* all three hold to within rounding. If not, we've misunderstood something, and it's
better to find out now. *Cost:* seconds.
*Learn:* that HotSpot is a linear RC network. This sets up the predictor in Phase E.

### Phase B: Understanding the simulator (RQ1)

**B1 [CORE] Block vs grid model, and grid resolution.**
Run EV6 with the block model and with the grid model at 16, 32, 64, 128 and 256. Compare
per-block temperatures against the 256 grid as the reference, and record runtime.
*Expect:* the block model is close for compact blocks but off for long, thin blocks (the
HotSpot 4.0 paper's finding). The grid result converges by about 64. Our first test already
shows Dcache at 338.9 K (block) vs 335.9 K (grid 64), a 3 K difference.
*Output:* error-vs-runtime plot. *Cost:* minutes.
*Learn:* modelling resolution and the accuracy/speed trade-off, which justifies the setting
used in later experiments.

**B2 [CORE] Power density: same power, smaller chip.**
Keep EV6's relative layout but scale the die from 8 mm to 24 mm per side (power fixed). Also:
keep the die fixed and scale only IntReg's area.
*Expect:* T_peak rises as power density rises, roughly as 1/area for the local hot spot.
This is the core reason chips get hotter at each technology node.
*Learn:* the difference between power and power density, which is the most important idea in
the field.

**B3 [CORE] Cooling and package sensitivity.**
One-at-a-time sweep: `r_convec` (fan/heat-sink quality, 0.05–1.0 K/W), TIM thickness and
conductivity, spreader thickness, ambient temperature, die thickness. Present as a "tornado"
chart of which knob moves T_peak the most.
*Expect:* `r_convec` dominates T_avg. TIM and spreader mostly affect *local* hot spots.
Ambient shifts everything equally.
*Learn:* the vertical heat path and why packaging matters as much as layout.

**B4 [OPT] Transient behaviour and time constants.**
Apply a power step (idle → busy) and record the temperature rise over time. Fit time
constants. Vary `sampling_intvl` (0.1 ms–10 ms).
*Expect:* a fast component (silicon, about milliseconds) and a slow one (heat sink, tens of
seconds). The example's 1 s trace never reaches true steady state on its own.
*Learn:* why the examples first run steady state and then use it as the initial temperature,
and why DTM can react fast while sinks warm slowly.

### Phase C: Floorplan studies (RQ2, RQ3), the heart of the project

Uses `flpgen.py` to make **synthetic floorplans** in which one property changes at a time.

**C1 [CORE] Where should the hot block go?**
On a 10×10 mm die with uniform low-power "background" tiles, place one high-power block at the
centre, at an edge midpoint, and in a corner. Then place two hot blocks adjacent, a quarter of
the die apart, and on opposite corners.
*Hypothesis (to test, not a known result):* corner and edge placement is likely *hotter* than
centre placement. There's less surrounding silicon to spread heat into, and the die edge does
not conduct heat sideways out of the chip. The heat spreader underneath may partly
compensate, which is exactly why it's worth simulating. Separating hot blocks lowers T_peak,
and clustering creates a single much hotter spot.
*Output:* heat maps (grid model) and a T_peak table.
*Learn:* lateral heat spreading, the physical basis of thermal-aware floorplanning.

**C2 [CORE] Multi-core layouts and "which cores to switch on."**
Generate N-core chips (4, 9, 16 cores in a grid, with an L2/cache region). For a 16-core chip
with only 4 cores active (the "dark silicon" situation), compare activation patterns:
clustered block, row, diagonal, checkerboard, and spread to the corners. Also try die aspect
ratios 1:1, 2:1 and 4:1 with the same area.
*Expect:* spread or checkerboard patterns are several °C cooler than clustered ones at
identical total power. I don't have a confident prediction for the aspect-ratio sweep; it's
an open question for us.
*Learn:* the bridge from floorplanning to *run-time* thermal management (task mapping), which
connects to Prof. Kedia's DTM and mapping work.

**C3 [CORE] Thermal-aware floorplanning with HotFloorplan (replicates JILP 2005).**
Run `hotfloorplan` on the EV6 block description with the default weights, then with the
temperature weight set to zero (area and wire length only). Simulate both resulting floorplans
with HotSpot using the gcc power.
*Expect:* the thermal-aware floorplan has a lower T_peak and a smaller gradient, but a similar
T_avg (the paper's key observation), at some cost in wire length or area.
*Cost:* about 90 s per floorplan.
*Learn:* simulated annealing, the cost function, and that floorplanning *redistributes* heat
rather than removing it.

**C4 [OPT] Pareto front: temperature vs wire length vs area.**
Sweep `lambdaT` and `lambdaW` (about 20–40 runs; with several random seeds, roughly
1 h in parallel). Plot T_peak against total wire length.
*Learn:* multi-objective optimisation and how to present trade-offs.

**C5 [OPT] Hand-designed EV6 variants.**
Hand-edit ev6.flp: move the integer register file next to the L2 cache; swap IntExec and FP
units; and so on. Predict the result *before* simulating, then check. A good exercise for
building intuition.

### Phase D: 3D, 2.5D and beyond (RQ4), linked to Kedia's research

**D1 [CORE] 3D stacking: which die goes near the heat sink?**
Using an `.lcf` stack (as in example3): a hot "logic" die and a cooler "memory" die, with a TIM
or bonding layer between. Swap their order. Vary the number of memory layers (1, 2, 4) and the
inter-layer thickness and conductivity.
*Expect:* the layer *farthest* from the sink is the hot spot, even if it dissipates less
power. This reproduces CoMeT's 3D-stacked finding in simplified form. Putting the hot logic
next to the sink is the right choice.
*Cost:* grid model, steady state only, seconds to minutes per configuration.
*Learn:* vertical heat flow and why 3D chips are thermally hard, with a direct link to the
professor's papers.

**D2 [OPT] 2.5D chiplets: spacing vs temperature (a mini TAP-2.5D).**
Four chiplets on an interposer floorplan. Sweep the gap between them (0–5 mm) with fixed
power, and report T_peak against total footprint and a wire-length proxy.
*Expect:* diminishing returns. The first millimetre of spacing helps most.
*Learn:* the chiplet design problem currently common in industry.

**D3 [OPT] Microfluidic (liquid) cooling.**
Example5 now runs (HotSpot rebuilt with SuperLU). Sweep pumping pressure and inlet temperature,
and compare against air cooling for the same stack.
*Learn:* advanced cooling. This is mainly "it's possible" content and gives less insight per hour.

**D4 [OPT] Leakage–temperature feedback (linked to Kedia's FastCool).**
Model leakage as P_leak(T) = P0·exp(β(T − T0)). Iterate: HotSpot → temperature → new
leakage → HotSpot, until it converges. Sweep cooling quality (`r_convec`) and find where the
iteration no longer converges (*thermal runaway*).
*Learn:* the positive feedback loop at the centre of Kedia's 3D-memory papers.

**D5 [OPT, stretch] Simple DTM emulation.**
Run a transient in short chunks. After each chunk, if T_peak exceeds the threshold, scale the
next chunk's power down (throttle) until the chip cools. Compare peak temperature and
"performance lost" (time throttled) for different thresholds.
*Learn:* closed-loop thermal management, which is what CoMeT does properly. Also shows the
limitation of pre-recorded power traces.

### Phase E: The lightweight thermal predictor (RQ5)

**E1 [CORE] Exact linear predictor for a fixed floorplan (superposition).**
For a floorplan with N blocks, run HotSpot N times, each with 1 W in one block only. This
gives the N×N *thermal influence matrix* R. Then for any power vector P:
T = T_ambient + R·P. Validate on random power vectors and on the gcc trace.
*Expect:* error about 0 K (exact up to solver tolerance), at microseconds per prediction
instead of seconds.
*Learn:* superposition, linear systems, and that "the simulator" is just a matrix for a
fixed design. Every ML model must beat this baseline where it applies.

**E2 [CORE] Learned predictor across *different* floorplans.**
The matrix trick breaks when the floorplan changes, so learning is needed there.
1. Generate a dataset: about 2,000–5,000 random floorplans × random power (block and grid
   64×64; about 1–2 h in parallel).
2. *Model 1 (simple, interpretable):* per-block regression (linear, then gradient boosting)
   on hand-made features: own power density, area, aspect ratio, distance to die edge, power
   of neighbours within radius r, total chip power.
3. *Model 2 (image-based):* small CNN / U-Net from power-density map (64×64) to temperature map
   (64×64), as in ThermEDGe.
4. Report MAE / max error (K), and prediction time vs HotSpot.

*Hypothesis:* the CNN does better than boosting on full spatial maps, and both are orders of
magnitude faster than HotSpot. Published learned predictors report errors around 0.3–1 K
within a design family (see lit_review.md §4). That gives a reasonable target, not a
guarantee.
*Learn:* dataset generation, feature engineering, train/validation/test methodology, and
surrogate modelling.

**E3 [OPT] Generalisation stress test.**
Train on one family (for example grid-of-cores chips) and test on another (random slicing
floorplans, different die size, different cooling). Then fine-tune with 10–50 samples of the
new family.
*Expect:* large error on unseen families, recovering with a few samples. This mirrors the
IC-ThermBench finding.
*Learn:* the main open problem in ML for EDA, and the honest reporting of limitations.

---

## 4. Suggested schedule (adjust to your deadline)

| Week | Work | Deliverable |
|---|---|---|
| 1 | Read the beginner guide and lit review; build infrastructure; A1, A2 | Working pipeline, sanity-check plots |
| 2 | B1, B2, B3 (+B4) | "How the simulator behaves" section |
| 3 | C1, C2, C3 (+C4/C5) | "What floorplans do" section, heat maps |
| 4 | D1 (+D2/D4) | 3D section linked to Kedia/CoMeT |
| 5 | E1, E2 (+E3) | Predictor section: accuracy and speed table |
| 6 | Write-up, slides, cleanup | Report and presentation |

**Minimum viable project** (if time is short): A1, A2, B1, B3, C1, C2, C3, D1, E1, plus a simple
E2 (gradient boosting only).

---

## 5. Risks and assumptions

| Risk | Mitigation |
|---|---|
| **No real workload power data** beyond the EV6/gcc example | Use the gcc trace plus documented synthetic power (uniform, random, "hot core" patterns). Check with the professor. A stretch option is generating real power with CoMeT/Sniper+McPAT, but that is a large setup effort and I'd treat it as out of scope |
| Trace-based simulation ignores feedback (throttling, contention), the limitation CoMeT highlights | State it in the report. D5 demonstrates the effect in a simplified way |
| HotSpot is a compact model, not ground truth | Cite its validation papers. Never claim absolute accuracy below about 1–2 °C |
| Synthetic floorplans may be unrealistic | Anchor everything with EV6 results. Keep power densities in realistic ranges (≈0.01–3 W/mm², as in EV6) |
| Long runs interrupted (PC sleep) | Sweeps write results incrementally and can resume |
| Without SuperLU, grid sizes must be powers of two | Already handled: HotSpot rebuilt with SuperLU |

---

## 6. Decisions I need from you

1. Which **[OPT]** experiments to include. My recommendation: B4, C4, D4, E3.
2. Team size and deadline, to size the scope.
3. Whether the professor expects real (McPAT/CoMeT) power or accepts synthetic power.
4. Whether to set up the git repo and directory structure now (recommended next step).
