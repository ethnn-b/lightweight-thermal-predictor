# Dataset and reference works

This file describes the data the TAs gave us, what it does and does not contain, and how we use it.
It also summarises the two research works the TAs pointed to (IC-ThermBench and ATPlace2.5D). How
each item feeds into the experiments is in `plan.md` §4 and §5.

Checked on 2026-10-30. Local copy: `Dataset/Sample_dataset/`. The same files are committed on
branch `p0-flpgen` under `data/sample_dataset/`.

---

## 1. TA sample dataset

### 1.1 What the TA said

- It is a *starting point* for thermal simulation, design-space exploration, and training and
  evaluating lightweight temperature predictors.
- It covers only a few configurations. We are *encouraged to expand it* by changing core types,
  number of cores, core and die sizes, and power profiles.
- **Focus on the 2D heterogeneous floorplans.** The 3D floorplans are outside the current project
  scope.

### 1.2 Layout

```
Sample_dataset/
├── README.md
├── 2D_floorplans/                 <- what we use
│   ├── Style_1/ fp_001 … fp_003   (3)
│   ├── Style_2/ fp_001 … fp_005   (5)
│   ├── Style_3/ fp_001 … fp_005   (5)
│   └── Style_4/ fp_001 … fp_010   (10)
│       fp_XXX/
│         fp_XXX.lcf               layer configuration (HotSpot -grid_layer_file)
│         fp_XXX_layer_0.flp       silicon layer: cores + zero-power FILL blocks
│         fp_XXX_tim.flp           TIM layer: one block covering the whole die
│         fp_XXX_steady.ptrace     one row of power (W per block)
│         fp_XXX_transient.ptrace  200 rows of power
│         fp_XXX_layer_0.png       floorplan picture
└── 3D_floorplans/                 <- out of scope (2_layer: 5, 4_layer: 9)
```

### 1.3 File formats (from the TA README, checked against the files)

- **`.flp`**: `name width height left-x bottom-y`, in metres. Each layer covers the whole die.
  Unused area is filled with `FILL_*` blocks that dissipate 0 W.
- **`.lcf`**: 7 lines per layer: layer number, lateral heat flow (Y/N), dissipates power (Y/N),
  volumetric heat capacity (J/m³K), resistivity (m·K/W), thickness (m), floorplan file. Every 2D
  floorplan has the same two-layer stack:

  | Layer | Role | Power | Heat capacity | Resistivity (k) | Thickness |
  |---|---|---|---|---|---|
  | 0 | Silicon (cores) | Y | 1.75e6 | 0.01 (k = 100 W/m·K) | 150 µm |
  | 1 | TIM | N | 4e6 | 0.25 (k = 4 W/m·K) | 20 µm |

- **`.ptrace`**: a header line with block names, then one row of watts per block. Columns follow
  the block order of the power layers in the `.lcf`. FILL blocks appear with 0 W. In transient mode
  each row is one `sampling_intvl` step.

### 1.4 Running HotSpot the TA way

```
hotspot -c hotspot.config -f fp_001_layer_0.flp -p fp_001_steady.ptrace \
        -grid_layer_file fp_001.lcf -model_type grid -steady_file fp_001.steady
```

- This is HotSpot's **grid model** with a layer file. The README says 64×64 grid. HotSpot only
  accepts `-grid_layer_file` with `-model_type grid`, so the TA flow is not the block model.
- **`hotspot.config` is not included.** The README only says the sink and spreader must be larger
  than the die (largest 2D die: 14 mm; largest 3D die: 16.5 mm). HotSpot's `example1` config
  (spreader 30 mm, sink 60 mm, ambient 45 °C, `r_convec` 0.1 K/W) meets that. We use it with
  `grid_rows = grid_cols = 64` until the TA tells us otherwise (see `plan.md` §10).
- With the grid model, `-steady_file` still gives one temperature per block (by default the
  average over the block's grid cells; `-grid_map_mode` can switch it to max, min or centre).
  `-grid_steady_file` gives the full 64×64 map.

### 1.5 What is in the 2D floorplans

All 23 2D floorplans have the **same set of cores and the same total power**. Only placement, die
size and white space change.

| Property | Value in every 2D floorplan |
|---|---|
| Cores | 8: **2 big** (4 × 4 mm) + **6 little** (2 × 2 mm) |
| Power in the given ptraces | big 20 W, little 8 W; 88 W in total |
| Power density | big 1.25 W/mm², little **2.0 W/mm²** (little cores are denser) |
| Power inputs per floorplan | 8 (FILL blocks are always 0 W) |
| Output blocks | 8 cores + 1 to 17 FILL blocks |

| Style | Count | Die sizes (mm) | Cores / die area | FILL blocks | What varies |
|---|---|---|---|---|---|
| Style_1 | 3 | 9×10, 9×11, 16×8 | 44–62 % | 3 | Big cores side by side, little cores in a cluster |
| Style_2 | 5 | 10×8, 9×10, 12×6, 10×6, 10×6 | 62–93 % | 1–4 | Dense packing, little white space |
| Style_3 | 5 | 7×14, 13×12, 14×6, 6×14, 14×6 | 36–67 % | 3–12 | Spread out, elongated dies |
| Style_4 | 10 | **14×14 for all** | 29 % | 10–17 | Same die; cores scattered in different positions |

Style_4 is especially useful: ten floorplans with the same die, the same cores and the same power.
Only the **positions** of the cores differ. It is a clean test of "does position matter, or only
core type?" (`plan.md` P1-3).

### 1.6 Power ranges (TA README)

| Core type | Range to sample from | Given ptraces |
|---|---|---|
| Big / P-core | 10–20 W | 20 W |
| Little / E-core | 5–10 W | 8 W |

The TA says these are practice values, not real ones. Real power could later come from
`turbostat` or Intel RAPL. These ranges replace the ones in our earlier plan (big 1–8 W, little
0.2–1.5 W), which were too low for these core sizes.

### 1.7 Problems found in the data

1. **The transient ptraces never change.** All 200 rows are identical to the steady row in all 23
   floorplans (0 changes between rows). They are templates for the file format, not workloads. We
   must generate our own transient power traces.
2. **Style_2 puts big-core power on little cores.** In Style_2 fp_001, fp_002, fp_003 and fp_005,
   the 20 W values go to `Core_0` and `Core_1`, which are 2×2 mm little cores, while the 4×4 mm big
   cores get 8 W. That makes 5 W/mm² on a little core. The ptrace seems to assign power by core
   index, not by core size. Style_2 fp_004 and all other styles are consistent. We regenerate all
   power from block sizes, so this does not affect us. We should still tell the TA.
3. **No HotSpot outputs.** There are no `.steady`, `.ttrace` or grid maps. All temperatures come
   from our own HotSpot runs.
4. **No shared cache or other non-core blocks.** White space is plain zero-power fill. Our scope
   document promises floorplans with a shared cache, so we keep one floorplan of our own with an L2
   (HET-A, already on branch `p0-flpgen`).
5. **No `hotspot.config`** (see §1.4).

### 1.8 How we use it

| Use | How |
|---|---|
| **Main benchmark floorplans** | All 23 2D floorplans replace our made-up HET-B and HOM-16 as the main test set. Results are reported per floorplan and summarised per style. |
| **Calibration cost** | Only 8 inputs per floorplan, so S1/T3 calibration is 8 HotSpot step runs. All 23 floorplans need 184 runs in total. |
| **"Is calibration needed?"** | Style_4: same die, same cores, only positions differ. Use one floorplan's coefficients on another, or a per-core-type model, and measure the error. |
| **Layout effects** | Die size and white space vary a lot (29–93 % core area). Show how self-heating, coupling and peak temperature depend on them. |
| **Hot spots inside cores** | The grid model gives the 64×64 map for free, so we can calibrate a "hottest cell per core" predictor (scope risk: block model hides hot spots). |
| **Power** | Random steady vectors and generated transient traces, all within the TA ranges, assigned by core size. |
| **Expanding the dataset** | See §1.9. |
| **3D floorplans** | Not used (TA advice). |

### 1.9 Generating more data (what the README and the TA ask for)

The README calls the files "templates for generating more data" and Style_1–4 "floorplan
generation styles". It says to vary the power "by hardcoding it" within the ranges of §1.6. The TA's
email asks us to expand the data by varying core types, number of cores, core and die sizes, and
power profiles. The dataset has no temperatures, so new data always means new inputs plus our own
HotSpot runs.

| What to generate | How | Used for | Priority |
|---|---|---|---|
| **Power inputs** for the given floorplans | `powergen.py`: random steady vectors and phase-based transient traces within the TA ranges, assigned by core size, in the TA's `.ptrace` format | Calibration traces (T2) and all test sets | CORE |
| **More floorplans in the TA's styles** (same 2 big + 6 little cores) | `flpgen.py` copies each style's recipe (§1.5): about 10 per style, so Style_1–3 match Style_4's 10. Writes `.flp`, `_tim.flp`, `.lcf` (same layer stack) | More layouts for P1-3(d) and P2-2; results per style rest on 10 samples, not 3 | CORE |
| **Other core counts and sizes** | `flpgen.py` with 4, 12, 16 and 32 cores, other big/little ratios, other die sizes and white space | Shows calibration works beyond the TA's 8-core case (P4-1); S2 model size (P3-3) | Stretch |
| **A third core type** | e.g. a mid-size core (3×3 mm) or a GPU block with its own power range (to choose; the TA gives none) | Heterogeneity beyond big/little | Stretch |
| **Real power** | turbostat / Intel RAPL on a real machine (README: "in future") | Realistic workload traces | Not planned |

Rules for generated floorplans: same file format and layer stack as the TA's, FILL blocks for white
space so every layer covers the die, die no larger than the spreader (30 mm), and generated
floorplans are always reported separately from the 23 given ones. The given floorplans stay the
main benchmark.

---

## 2. IC-ThermBench

**Full title:** *IC-ThermBench: An Open, Progressive Benchmark for Generalizable 2.5D/3D-IC
Thermal Learning.* D. Hang, W. Yang, K. Ding, H. Xin, J. Wei (UTS, ShanghaiTech, TU München).
arXiv:2608.23977 (cs.CE), v1 25 Aug 2026, v3 29 Oct 2026. Preprint; no peer-reviewed venue yet.
Code: https://github.com/Day333/ThermalBench (MIT). Data: CC BY 4.0, on Google Drive, Zenodo
DOI 10.5281/zenodo.21992816.

### 2.1 What it is

A benchmark for **learned thermal surrogates** (neural networks that map a power map to a
temperature map) for **2.5D chiplet systems**. Its aim is generalisation: one network that
predicts temperature for many placements, materials and package settings it has never seen. That
is the opposite of our design, which is a tiny model calibrated for one floorplan.

### 2.2 Contents

| Scope | What changes between samples | Samples | Inputs per grid cell |
|---|---|---|---|
| S1 | Source suite: Alpha EV6 and industrial tasks (11 tasks); has **transient** tasks (HotSpot single/quad/octa-core, industrial 8C/32C) | not reported | varies |
| S2 | Chiplet placement and orientation | 15,000 | power, x, y |
| S3 | + filler conductivity (0.2–5 W/m·K) | 15,000 | + k |
| S4 | + ambient (25–55 °C) and convection (500–20,000 W/m²K) | 15,000 | + T_amb, h, R_conv |
| S5 | Five unseen package cases (11–15), zero-shot and few-shot | 5,000 | as S4 |

- Splits for S2–S4: 10,800 train / 1,200 val / 3,000 test, by index.
- **Ground truth:** HotSpot, grid-based detailed-3D mode, 64×64, steady state. The stack is a
  six-layer 2.5D stack (substrate, C4 underfill, silicon interposer, µbump underfill,
  chiplet/filler, TIM), copied from ATPlace2.5D's Cases 1–10.
- **Format:** `input.mat` (B, P, Z, X, Y) and `output.mat` (B, Z, X, Y), float32, temperature in K.
  About 4.8 GB for S2–S5; checkpoints about 27.5 GB.
- **Power input** is each chiplet's power painted over its grid cells. It is not a per-core power
  vector for one fixed floorplan.

### 2.3 Headline results (RMSE in K; to be re-checked against the paper's tables before citing)

| Model | S2 | S3 | S4 | S5 zero-shot |
|---|---|---|---|---|
| U-FNO | 0.44 | 0.67 | 0.94 | 28.2 |
| Therm-FM-L (their foundation model) | 0.35 | 0.74 | 0.81 | 15.3 |
| Therm-FM-T | 0.58 | 0.91 | 1.05 | 8.7 |
| DeepOHeat | 3.71 | 3.97 | 4.74 | 24.0 |

With 10 labelled samples of an unseen case, the best error drops to about 2 K. Inference time is
not reported. Training takes 15 minutes to 6 hours on an RTX A6000 GPU. Note: the arXiv abstract
page lists different (worse) S4/S5 numbers than the HTML paper and the README, so check the final
version.

### 2.4 How it relates to us, and how to use it

- **Not a source of training data for us.** It is 2.5D chiplets on an interposer, steady state
  only (outside S1), with no fixed floorplan seen under many power inputs. Our calibration needs
  exactly that, and our scope is 2D heterogeneous cores.
- **A comparison point for the report.** Even in the easiest setting, the best networks are off by
  about 0.35 K RMSE, use GPU-trained models of megabytes to gigabytes, and break on unseen packages
  (8–40 K zero-shot). Our calibrated linear model should be at ≪ 0.1 K with a few hundred bytes,
  because it is calibrated for the floorplan it predicts. That is the case for the two-stage
  "calibrate, then predict" design, in numbers from someone else's paper.
- **It supports our P1-3 result.** Its S5 failure shows that a model which is *not* calibrated to
  the floorplan and package can be badly wrong. Its few-shot track (K = 10 to 500 labels per case)
  is the learned version of our calibration stage; we need only N = 8 step runs.
- **Ideas we reuse:** the 64×64 HotSpot grid setup (same as the TA flow), and the way they vary
  ambient and convection (used in our P4-2 recalibration test). Note that a change of ambient only
  shifts T_amb in our model and needs no recalibration; a change of convection does.
- **Optional:** S1's HotSpot transient tasks (EV6 single/quad/octa-core) could serve as extra
  transient test traces for an EV6 sanity check, if their format turns out to contain per-block
  power traces. Not checked yet; low priority.

---

## 3. ATPlace2.5D

**Full title:** *ATPlace2.5D: Analytical Thermal-Aware Chiplet Placement Framework for
Large-Scale 2.5D-IC.* Q. Wang, X. Li, T. Jia, Y. Lin, R. Wang, R. Huang. ICCAD 2024.
Paper: https://dl.acm.org/doi/10.1145/3676536.3676648. Code: https://github.com/Brilight/ATPlace_pub
(newer version said to be at PKU-IDEA/ATPlace_pub). No license file found.

**Caveat:** we could not open the paper itself (the ACM site refused automated access), and the
placement kernel in the public repo is encrypted. What follows comes from the repo. Read the paper
through the institute library before quoting anything about its thermal model.

### 3.1 What it is

A placer that decides where chiplets go on an interposer. It minimises wirelength plus a thermal
penalty above a temperature threshold. The repo says it builds a "compact analytic thermal model"
and passes it to the placement kernel. A thermal-aware placer has to evaluate temperature
thousands of times during optimisation, so it needs a fast thermal model. That is the same need
our predictor serves for DTM.

### 3.2 What is in the repo

- **Reference solver: HotSpot**, grid model, `-detailed_3D on`, with a layer file
  (`"thermal_solver": "hotspot"`). `Thermal.py` writes the `.flp`, `.lcf`, `.ptrace` and config
  for each case and times the HotSpot call.
- **Ten benchmark cases** (`cases/Case1` … `Case10`) in Bookshelf format (`.blocks`, `.nets`,
  `.pl`, `.power`). Example, Case1: one CPU (12×12 mm, 105 W), two GPUs (18×18 mm, 300 W each),
  three HBM stacks (8×12 mm, 25 W each); 780 W in total.
- Running it needs Gurobi and the authors' environment.

### 3.3 How it relates to us, and how to use it

- **Not data for our predictor.** It is chiplet placement at hundreds of watts, not
  per-core temperatures on one die.
- **Useful HotSpot scripting reference.** `Thermal.py` is a worked example of writing a layer file
  and calling HotSpot's grid model from Python, which is what our `run_hotspot.py` (P0-4a) does.
- **It motivates the use case.** A placer, like a DTM controller or a scheduler, calls the thermal
  model in a loop and cannot afford a HotSpot run each time. Our P6-3 demo ("which cores to switch
  on") is the core-level version of the same problem.
- **It is the origin of IC-ThermBench's stack.** IC-ThermBench Cases 1–10 are ATPlace2.5D's cases.
- **To check when we get the paper:** whether its thermal model is a superposition of
  pre-computed per-chiplet responses (a Green's-function / influence-matrix idea, the steady
  analogue of our G), how it is fitted to HotSpot, and its reported speed-up and error. If it is,
  it is a direct citation for model S1 and belongs in `lit_review.md` §3.1.

---

## 4. Summary: what changes because of this data

| Before (plan of 17 Oct) | Now |
|---|---|
| Our own HET-A, HET-B, HOM-16 floorplans | The TA's 23 2D floorplans are the main set; HET-A (with L2) and EV6 stay as extras |
| HotSpot block model, example1 config | HotSpot **grid model 64×64 with the TA's `.lcf`**; block temperatures from the grid; full maps available |
| Power: big 1–8 W, little 0.2–1.5 W | Big 10–20 W, little 5–10 W (TA ranges) |
| N ≈ 10–20 blocks | N = 8 power inputs per floorplan (2 big + 6 little) |
| Transient test traces: synthetic | Still generated by us; the TA transient ptraces are constant |
| "Is calibration needed?" on 2 floorplans | On 23 floorplans, including 10 with the same die (Style_4) |
