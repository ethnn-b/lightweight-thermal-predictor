# HotSpot for Dummies: the beginner's guide to our project

This is the companion to `plan.md`. The plan says *what* we do; this guide explains *why*, and
what you need to understand to do it. No prior knowledge assumed.

- **Part A** explains the concepts, from "why chips get hot" up to "proactive DTM". Read it once,
  top to bottom.
- **Part B** goes through the experiments in `plan.md` one by one: the goal, which concepts from
  Part A you need, the steps, what you should see, and when it counts as done. Owners (E or K)
  are as in `plan.md` §12.

---

# Part A: Concepts

## A1. Why chips get hot

A processor is billions of tiny switches (transistors). Each switch uses a little electrical
energy, even when idle, and **all of that energy ends up as heat**. A laptop CPU turns about
15–45 W into heat, a desktop or server chip 100–400 W, and that heat leaves through an area about
the size of a fingernail.

Heat is a problem because:
- hot transistors switch more slowly, so the chip must run slower;
- heat speeds up wear-out, so chips age faster;
- hot transistors **leak** more current, which makes more heat, which makes more leakage (A10);
- chips have a hard limit, typically 85–105 °C, above which they must slow down.

**Hot spot.** Heat is not spread evenly. A small, busy part of the chip can be 20–30 °C hotter
than a quiet part. In our example1 run, the integer register file reached about 70 °C while the
L2 cache sat at about 51 °C. The **peak** temperature, not the average, decides whether the chip
must slow down.

**Power vs power density.** *Power* (W) is heat per second. *Power density* (W/mm²) is heat per
second per unit area. Of two blocks with the same power, the **smaller one gets hotter**, because
its heat is squeezed through less area. In EV6, the register file has about 2.9 W/mm² and the
floating-point queue about 0.017 W/mm², 170× less. This idea comes back with big and little cores
(A6).

## A2. Heat behaves like electricity

| Heat | Electricity |
|---|---|
| Temperature difference (K or °C) | Voltage (V) |
| Heat flow = power (W) | Current (A) |
| **Thermal resistance** R (K/W): how hard it is for heat to pass | Resistance (Ω) |
| **Thermal capacitance** C (J/K): how much heat a material soaks up before it warms | Capacitance (F) |

"Ohm's law for heat": **temperature rise = power × thermal resistance.** Example: the heat sink to
air resistance in our config is `r_convec = 0.1 K/W`; at 40 W the heat sink sits about
40 × 0.1 = 4 K above the air.

**Resistance decides the final temperature. Capacitance decides how fast you get there.**
The product R × C is the **time constant τ** (seconds). After a power step, temperature covers
about 63 % of the way to its final value after one τ, and about 99 % after five τ.
Thin silicon has τ of milliseconds. A big copper heat sink has τ of tens of seconds. This
"fast part plus slow part" behaviour shapes every transient model in this project (A9).

**Kelvin vs Celsius:** HotSpot works in Kelvin. A *difference* of 1 K is the same as 1 °C.
°C = K − 273.15, so HotSpot's default ambient of 318.15 K is 45 °C.

## A3. What is between the chip and the air

```
        air  (ambient, 45 °C inside a PC case)
   ┌────────────────────────────┐
   │        HEAT SINK (fins)    │  big, slow to warm up (τ ≈ tens of seconds)
   └────────────────────────────┘
       ┌────────────────────┐
       │   HEAT SPREADER    │      copper plate, spreads heat sideways (τ ≈ 0.1–1 s)
       └────────────────────┘
           ┌────────────┐
           │    TIM     │          thermal paste: thin, but a poor conductor
           ├────────────┤
           │ SILICON DIE│          the chip, where the power is produced (τ ≈ ms)
           └────────────┘
```

Heat also moves **sideways** inside the silicon and the spreader. That is why a core next to a
hot GPU runs hotter than the same core next to a cool cache: neighbours heat each other. This
**coupling** between blocks is exactly what our predictor's coefficients capture.

## A4. HotSpot in one page

**HotSpot** is a free *compact thermal model* from the University of Virginia. It turns the chip
and package into an RC circuit (A2) and solves it. It is fast (milliseconds to seconds) and
accurate to within a few degrees of detailed tools, which take hours.

**Inputs** (all lengths in metres, power in watts):

| File | What it is | Example |
|---|---|---|
| `.flp` floorplan | One rectangle per block: `name width height left-x bottom-y` | `L2 0.016 0.0098 0 0` |
| `.ptrace` power trace | Header of block names, then one row of watts per time step | `gcc.ptrace`: 100 rows |
| `.config` | Package and physics settings, `-option value` per line | `-ambient 318.15`, `-r_convec 0.1`, `-sampling_intvl 0.01` |
| `.init` | Start temperature of every node, for a transient run | usually a copied `.steady` file |

The settings you will touch: `-ambient`, `-r_convec` (heat sink quality), `-sampling_intvl`
(seconds per power row, our Δt), `-model_type` (`block` or `grid`), `-grid_rows/cols`,
`-leakage_used`. Any option can also be given on the command line.

**Outputs:**

| File | What's in it |
|---|---|
| `.steady` | Final temperature (K) of every node: blocks first, then package nodes |
| `.ttrace` | Transient: one row of block temperatures (K) per time step |
| `.grid.steady` | Grid model: temperature of every grid cell |

The extra names in `.steady` are package nodes: `iface_X` (TIM above block X), `hsp_X`
(spreader above X), `hsink_X` (sink above X), `inode_N` (parts of spreader and sink beyond the
die edge). Heat flows up: IntReg 342.4 K → iface 339.6 → hsp 327.2 → hsink 324.8 → air 318.15.

> **Watch out:** HotSpot prints temperatures with only **2 decimals** (0.01 K). For calibration
> we patch this to 6 decimals (plan P0-4a).

**Steady state vs transient.**
- *Steady state:* "if this power stayed on forever, where would temperature settle?" Uses only R.
- *Transient:* "how does temperature move over time as power changes?" Uses R and C, stepped
  through time with step Δt = `sampling_intvl`.

**Block model vs grid model.**
- *Block model:* one temperature per block, plus package nodes. Very fast (≈ 10 ms). This is our
  reference, because DTM works with one temperature per core.
- *Grid model:* chops the die into e.g. 64×64 cells. Slower (≈ 1 s), gives a real heat map. Shows
  the hottest point *inside* a big core, which the block model averages away (plan P0-3).

**How many nodes does the block model have?** For N blocks: N silicon + N interface + N spreader +
N sink nodes, plus 12 extra package nodes, so **4N + 12 nodes**. EV6 has 30 blocks, so 132 nodes.
We only *see* the N block temperatures. The other 3N + 12 are **hidden nodes** (A9.4).

## A5. Linearity and superposition: why a lightweight predictor is possible at all

With leakage off, HotSpot is a **linear** system:
- **Scaling:** double every block's power and every temperature *rise* (temperature minus ambient)
  doubles.
- **Superposition:** the rise from power pattern A plus pattern B equals the rise from A alone
  plus the rise from B alone.
- Zero power gives exactly ambient.

That means HotSpot's whole answer for a fixed floorplan can be captured by a modest set of
numbers measured once. That is calibration (A7). Experiment P0-2 checks this before we rely on it.

## A6. Heterogeneous cores

A **heterogeneous** chip has cores of different kinds on one die. Phones and laptops do this:
**big** cores (fast, large, power-hungry), **little** cores (slow, small, efficient), often a
**GPU**, plus a shared **L2 cache**. ("big.LITTLE" is Arm's name for this.) A **homogeneous** chip
has identical cores, e.g. our 4×4 HOM-16.

What changes thermally:
- **Area.** A little core is small, so 1 W in it gives a larger rise than 1 W in a big core
  (power density, A1).
- **Power range.** A big core may use 1–8 W, a little core 0.2–1.5 W.
- **Heat capacity.** Smaller blocks hold less heat, so they heat up and cool down faster.
- **Position.** A core at the die edge or corner has fewer places to spread heat sideways, and a
  core next to the GPU gets heated by it. Two cores of the *same type* can therefore behave
  differently.

The last point is why calibration is **per floorplan**, not per core type. Plan P1-3 shows it.

## A7. The two stages: calibration and prediction

Think of a kitchen scale: you **calibrate** it once with a known weight, then **weigh** things
quickly forever after.

- **Calibration** (one time per floorplan): run HotSpot a few planned times on the floorplan, and
  fit the predictor's **coefficients**: the numbers inside the model formula. Saved to a small
  file (`model.npz`). Slow is fine (seconds to minutes).
- **Prediction** (many times): given a power input, compute temperatures from the coefficients
  only. No HotSpot. Must be fast (microseconds) and small (kilobytes), because it runs inside a
  DTM controller every few milliseconds.

If you change the floorplan or the package (heat sink), the coefficients are no longer valid and
you calibrate again. If you change the *workload*, you do **not** recalibrate (A9.7).

## A8. Steady-state prediction

### A8.1 The influence matrix G (model S1)

Because of superposition (A5), the steady temperature rise of every block is a weighted sum of
all block powers:

```
T_i = T_amb + G_i1·P_1 + G_i2·P_2 + ... + G_iN·P_N       or in matrix form:  T = T_amb + G·P
```

**G_ij** (K/W) means "how many kelvin block i rises per watt in block j". G_ii is self-heating;
G_ij for i ≠ j is coupling.

**How to calibrate it:** run HotSpot N times. In run j, put 1 W in block j and 0 W everywhere else.
The temperature rises of all blocks in that run are column j of G. Done.

**Worked example (made-up numbers), 2 cores: big A and little B.**

| Calibration run | Rise of A | Rise of B |
|---|---|---|
| 1 W in A only | 0.8 K | 0.3 K |
| 1 W in B only | 0.3 K | 1.5 K |

So G = [[0.8, 0.3], [0.3, 1.5]]. B's self-heating (1.5) is larger than A's (0.8) because B is
smaller. To **predict** for P = (5 W, 1 W): rise of A = 0.8·5 + 0.3·1 = 4.3 K; rise of B =
0.3·5 + 1.5·1 = 3.0 K. Add ambient. That is 4 multiplications instead of a HotSpot run.

Two checks you get for free: **G is symmetric** (G_ij = G_ji; a property of RC networks called
reciprocity), and all entries are positive.

Model size: N² numbers. For N = 20 that is 400 numbers, 3.2 kB as float64.

### A8.2 Compressed G (model S2)

For a chip with many cores (e.g. 64), N² gets big (4,096 numbers). Can we store fewer?
You might think far-apart cores don't heat each other, so their G_ij ≈ 0 and can be dropped.
**That is wrong in HotSpot:** every watt anywhere warms the *shared* spreader and heat sink, so
every core rises a little from every other core's power. So S2 stores:
- **one shared "package" number** g0: the rise every core gets per watt of total chip power;
- for each core, its own self-heating and the extra coupling to its **k nearest neighbours**.

G_ij ≈ g0 + (local coupling if j is among i's k neighbours, else 0). Size ≈ N·(k+1) + 1 instead of
N². It trades a little accuracy for size. For our N ≈ 10–20 it isn't needed; it matters for the
model-size story at larger N.

### A8.3 Power blurring and the heat-spread kernel (model S0, the uncalibrated baseline)

S0 answers: *how well can you do without calibrating on this floorplan?*

**The heat-spread kernel.** Put 1 W into one tiny spot in the middle of a large die, and look at
the steady temperature rise across the die. You get a "hill": tall at the spot and falling off
with distance. The shape of that hill is the **kernel** (also called the thermal point-spread
function, or Green's function). It depends only on the *stack* (silicon thickness, TIM, spreader,
sink), not on the floorplan. So you measure it **once** with HotSpot and reuse it for every
floorplan.

**Power blurring.** Now take any floorplan and draw its power as a grid map (W per cell). Each cell
makes its own little hill, scaled by its power. The temperature map is the sum of all those
hills. Adding up shifted, scaled copies of one shape is called a **convolution**. It looks
exactly like blurring a photo: a sharp power map becomes a smooth temperature map, hence "power
blurring". With the FFT it takes well under a millisecond. To get a block's temperature, average
the map over the block's rectangle.

**Edges.** The die's sides are insulated, so heat near an edge has nowhere sideways to go and
bounces back, making edges and corners hotter. The usual trick is **mirroring**: pretend there are
mirror copies of the power map beyond each edge; their hills add the "bounced" heat.

**Why it is only a baseline.** It assumes the hill is the same shape everywhere on the die. In
reality it changes near edges (mirroring only partly fixes this), and the spreader and sink are
finite. So expect 1–3 K errors, mostly at edges. S1 *measures* the exact answer for this floorplan
instead. In fact S1's column j *is* the true "hill" for block j at its actual position. Comparing
S0 with S1 shows what calibration buys (plan P1-3).

## A9. Transient prediction

### A9.1 Step response and time constants

Turn on 1 W in block j at t = 0 and watch block i rise over time. That curve is the **step
response** G_ij(t). It starts at 0 and ends at G_ij, the steady value from A8.1. It doesn't follow
one smooth exponential. It rises quickly at first (silicon, ms), then slowly (spreader, ~1 s),
then very slowly (heat sink, tens of s).

### A9.2 Sum of exponentials (model T3)

We describe each step response as a few exponentials with **shared** time constants:

```
G_ij(t) = a_ij1·(1 − e^(−t/τ1)) + a_ij2·(1 − e^(−t/τ2)) + a_ij3·(1 − e^(−t/τ3))
```

e.g. τ1 ≈ 5 ms, τ2 ≈ 0.5 s, τ3 ≈ 30 s. The weights a_ij1 + a_ij2 + a_ij3 add up to G_ij.
**Calibration:** the same N runs as for G (A8.1), but run as transients long enough to settle;
fit the τ's and a's to the curves by least squares (A9.6).

**Prediction from power alone.** Keep, for every block j and every τ_m, a "leaky memory" of its
power:

```
z_jm[k+1] = α_m · z_jm[k] + (1 − α_m) · P_j[k]        with α_m = e^(−Δt/τ_m)
T_i[k]    = T_amb + Σ_j Σ_m  a_ijm · z_jm[k]
```

z_j1 forgets quickly (it follows recent power); z_j3 forgets slowly (it remembers the last
minute). These z's are the model's **state**. They are computed from the power trace only, so no
temperature input is ever needed. Start with z = 0 for a cold chip, or z = P[0] for a chip warmed
up at the first power row. Size: N²·M weights + M time constants.

### A9.3 State-space models (model T4)

A **state-space model** is the general form of "the state now plus the input now gives the next
state":

```
x[k+1] = A·x[k] + B·P[k]          (x = the state, P = power)
T[k]   = T_amb + C·x[k]           (what we observe: block temperatures)
```

HotSpot's RC circuit, sampled every Δt, is *exactly* this, with x = all 4N + 12 node temperatures
(A4). The maths that turns the circuit (C·dT/dt = −G·T + P) into A and B is the **matrix
exponential**; MatEx (lit review §3.2) is built on it. T3 is a special case of this form.

### A9.4 Hidden nodes, and why they matter

We observe N block temperatures, but the true state has 4N + 12 nodes. The hidden ones (spreader,
sink) store heat, and with it the *memory of past power*. Example: after a busy minute the sink is
warm, so a core cools down to a higher floor than after an idle minute, even if the core
temperature is the same right now. A model that only knows "current block temperatures + current
power" can't tell these two cases apart. So every transient model needs some way to remember the
past: extra exponentials (T3), several past values (T2), or the full state (T4).

### A9.5 Reduced models, and what "reduced state-space" means

The full state has 4N + 12 = 132 numbers for EV6, but many of them move together (the sink nodes
all rise almost in step). **Model-order reduction** finds a few combinations ("patterns") of the
state that capture almost all of how power affects block temperatures, and drops the rest.
**Balanced truncation** is the standard method: it ranks patterns by how much they matter from
input (power) to output (block temperature) and keeps the top r. It is like compressing an image
by keeping only its main components. Result: an A of r × r with r ≈ 5–15 instead of 132 × 132.
This is a *transient* idea. The steady-state equivalent is simply G (and compressed G, A8.2).

### A9.6 ARX (model T2), least squares, and where the "past temperatures" come from

**ARX** = *Auto-Regressive with eXogenous input*. For one core, with T meaning the rise above
ambient:

```
T[k+1] = a1·T[k] + a2·T[k−1]  +  b0·P[k] + b1·P[k−1]
         └ its own past ┘        └ the input "X" ┘
```

With N cores, each a and b becomes an N×N matrix, so each core's next temperature depends on all
cores' past temperatures and powers. The number of past values used is the number of **lags**
(here 2). More lags let the model remember more of the past (A9.4).

**Least squares:** run HotSpot once on a calibration trace (T2 in plan P1-2), write every time step
as one equation "T[k+1] = a1·T[k] + ...", and solve the whole pile of equations for the a's and b's
that fit best (NumPy `lstsq`). We also force the fitted model to have the correct steady value G
(**steady-gain constraint**), because a short trace barely shows the slow sink.

**Where do the past temperatures come from?** Your input is only a power trace, so:
- In **`transient`** (the core predictor), the model feeds its **own predictions** back in. Start
  from the initial temperatures, predict T[1], use it to predict T[2], and so on. Only power goes
  in. This is called *simulation* or *open-loop* mode. Errors can accumulate, which is what
  plan P3-1 measures.
- In **`forecast`** (DTM, plan P6), a real chip has **thermal sensors**, so at each step the model
  uses the *measured* current temperature and predicts a few steps ahead. In our experiments
  HotSpot's output plays the sensor.

T3 and T4 don't need past temperatures in either mode; their state comes from power alone. ARX is
in the plan because it is the classic run-time predictor (lit review §4) and needs only one
calibration trace instead of N runs.

### A9.7 Does the model depend on the workload or the mapping?

**No, not in principle.** The coefficients describe how *this floorplan and package* turn watts
into kelvin, and that is fixed physics. A **workload** (what programs run) and a **mapping** (which
core runs which program) only change the **input**: how many watts each core gets, and when.
Moving a task from core 2 to core 5 moves its watts from P_2 to P_5. The coefficients don't change.

Caveats:
- **Fitted models are only as good as their data.** T2 is fitted by least squares on one trace. If
  that trace only ever heats cores 1 and 2, or only changes slowly, the fit won't learn the rest,
  and will *look* workload-dependent. So the calibration trace is designed to excite every core
  **independently**, with both short and long phases (this property is called *persistent
  excitation*). It should not look like any one real workload.
- **Leakage** makes power depend on temperature, so the system stops being exactly linear (A10).
- A pure **AR** model (temperature history only, no power) *is* workload-dependent: it can only
  extrapolate the current trend and can't see a power change coming. That's why it's not in the
  plan.

Plan P4-1 checks all of this by testing on workloads and mappings unlike the calibration data.

### A9.8 Persistence (T0) and forecast horizon

**Persistence:** "the next temperature equals the current one." It costs nothing and is surprisingly
good for 1 ms ahead, because temperature moves slowly. Every forecaster must beat it.
**Forecast horizon:** how far ahead you predict (1, 10, 100, 1,000 ms). Errors grow with the
horizon. The error-vs-horizon curve (plan P3-2) tells DTM how far ahead it can trust the
predictor.

## A10. Leakage: when linearity breaks

**Dynamic power** comes from switching and depends on the workload. **Leakage power** flows even
when idle, and grows roughly exponentially with temperature. So hotter means more leakage, which
means more heat. With leakage on (`-leakage_used 1`), power depends on temperature and HotSpot is
no longer linear. Our coefficients then become approximations. The usual fix: predict T, compute
the leakage at that T, add it to the power, and predict again; repeat 2–3 times (a **fixed-point
iteration**). This is plan P4-3.

## A11. The metrics

**Accuracy** (always against HotSpot, in kelvin):
- **MAE** (mean absolute error): average of |predicted − HotSpot| over blocks (and time steps).
- **Max error**: the single worst |predicted − HotSpot|.
- **T_peak error**: |predicted hottest temperature − HotSpot's hottest temperature|. This is what
  DTM cares about most.
- **Hottest-core accuracy**: in what % of cases the predictor names the same hottest core as
  HotSpot.
- **RMSE** (root-mean-square error): like MAE, but punishes big errors more.

**Prediction time:** wall-clock time for one prediction (one `steady` call, or one transient step),
measured as the **median** over ≥ 10,000 calls after a warm-up, on one CPU thread. Unit: µs.
Compare with HotSpot's time for the same input. All final timings are measured on **one** laptop
(plan §13).

**Model size:** how many coefficients the model stores, and the bytes in its `.npz` file.
float64 = 8 bytes per number; float32 = 4.

**Calibration cost** (secondary): how many HotSpot runs and how many seconds calibration took.

**Pareto front:** with three metrics you can't always pick one "best" model. A model is on the
*Pareto front* if no other model is better in every metric at once. Plan P3-3 plots it.

## A12. DTM: dynamic thermal management

**DTM** = what a chip does at run time to stay below its temperature limit (e.g. 85 °C).

The knobs:
- **DVFS** (Dynamic Voltage and Frequency Scaling): lower a core's clock frequency f and voltage V.
  Dynamic power ∝ f·V², and V drops with f, so power falls roughly like f³. Halving the
  frequency cuts power by a large factor, but also halves the speed.
- **Throttling:** forcibly slowing down because of heat (DVFS, or pausing).
- **Task migration:** moving a task to another core, e.g. from a hot big core to a cool little
  core. It runs slower there, but the chip stays below the limit.

**Reactive vs proactive DTM.**
- **Reactive:** act when a sensor *already* reads above the limit, like a thermostat. Because heat
  takes time to move, the temperature keeps rising for a while after you act (*overshoot*). You
  therefore need hard throttling, and the limit is still sometimes violated.
- **Proactive:** use a **predictor** to see that the limit *will* be crossed, say, 50 ms from now,
  and act early and gently (one DVFS step down, or a migration). Fewer violations and less lost
  performance, *if* the predictor is accurate and fast. That is the wishlist in the problem
  statement (plan P6).

**Closed loop.** In DTM, the temperature changes the power (via throttling), which changes the
temperature. So the "chip" must accept a new power every interval. Terms: the **plant** is the
thing being controlled (HotSpot, stepped interval by interval; plan P6-1); the **controller** is
the DTM policy; the **sensor** is the temperature it reads; the **actuator** is the DVFS level or
migration it sets.

**Performance proxy:** we don't run real programs, so we measure lost performance as the sum over
time of each core's frequency, relative to running at full speed.

## A13. Our setup

```
 Windows (VS Code)                         Ubuntu in WSL (where simulations run)
 ──────────────────                        ─────────────────────────────────────
 VS Code with the WSL extension   ──────▶   ~/projects/ltp/   (our git repo, cloned here)
                                              HotSpot/ (submodule, built with SUPERLU=1 + precision patch)
                                              src/, experiments/, data/, results/
```

- **WSL** = Windows Subsystem for Linux: a real Linux inside Windows. HotSpot is Linux software.
- Clone the repo inside WSL (not `C:\`): file access is much faster.
- From Windows, Linux files are at `\\wsl$\Ubuntu\home\<user>\...`.
- See `plan.md` §13 for how E and K share work through GitHub.

## A14. Checklist before you start

You're ready when you can answer these without looking:

1. Why does 1 W heat a little core more than 1 W heats a big core?
2. What does one column of G mean, and how many HotSpot runs does it take to get all of G?
3. Why can't you drop the coupling between two far-apart cores to zero?
4. What is a heat-spread kernel, and why doesn't it need per-floorplan calibration?
5. Why does a transient model need memory of the past, even if it knows all current block
   temperatures?
6. In `transient` mode, where do ARX's past temperatures come from? In `forecast` mode?
7. If we move a task from a big core to a little core, do the coefficients change?
8. Why is proactive DTM better than reactive, and what does it need from the predictor?

(Answers: 1. Higher power density (A1, A6). 2. How much each block rises per watt in block j; N runs
(A8.1). 3. All cores share the spreader and sink (A8.2). 4. The temperature "hill" from a point of
power; it depends only on the stack (A8.3). 5. Hidden spreader and sink nodes store heat (A9.4).
6. Its own predictions; sensor readings (A9.6). 7. No, only the power input changes (A9.7).
8. It acts before overshoot; it needs accurate, fast forecasts (A12).)

---

# Part B: The experiments, one by one

Each experiment lists: **Owner**, **Goal**, **Concepts** (Part A sections to read first),
**Steps**, **What you should see**, and **Done when**. Every experiment ends with a
`results/<exp>/README.md` and, where models are evaluated, rows in `results/summary.csv`
(plan §13).

## J0. Agree on shared interfaces (E + K)

**Goal:** fix file formats and the model API before either of us writes models, so our parts plug
together. **Steps:** go through plan §12 J0 together (the model class methods, the `.npz` fields,
the `data/` layout, the `summary.csv` columns). Write them into `src/ltp/README.md`.
**Done when:** both agree and it's merged to `main`.

## Phase P0: Ground truth you can trust

### P0-1. Example1 reproduced (E, done)
See `README_SETUP.md`. HotSpot built, example1 run, outputs converted to CSV and plotted.

### P0-2. Linearity checks (E)
**Goal:** prove HotSpot is linear (A5) on our setup, so that later errors in S1/T2/T3 can only be
bugs or calibration problems, not physics.
**Concepts:** A4, A5.
**Steps:**
1. EV6, block model, steady state, constant power = the average row of `gcc.ptrace` → rise R1.
2. Same power ×0.5, ×2, ×3. Check that the rise scales by the same factor.
3. Two different power patterns A and B, then A+B. Check rise(A+B) = rise(A) + rise(B).
4. Zero power. Check every block is at ambient.
5. Repeat 2–3 for a short transient trace.
**What you should see:** differences at the level of HotSpot's printed precision (0.01 K before
the patch, ~10⁻⁶ K after).
**Done when:** a small table of max differences per check, all ≈ 0.

### P0-3. Block vs grid model on a big core (K)
**Goal:** find out how much hotter the hottest point inside a big core is than the block model's
single number for that core. If it's large, DTM needs a correction.
**Concepts:** A4 (block vs grid), A6.
**Steps:**
1. HET-A (from P0-5) at full load, block model, steady → one temperature per core.
2. Same with the grid model at 32×32, 64×64, 128×128 (`-model_type grid`, `-grid_steady_file`).
3. For each big core: max of its grid cells minus its block-model temperature. Time each run.
**What you should see:** a few kelvin of difference inside big cores (less for little ones), and
grid results that stop changing between 64 and 128.
**Done when:** a table "core, block T, grid max T, difference" and the runtime per resolution.

### P0-4a. Infrastructure: run, parse, sweep (E)
**Goal:** scripts so nobody types HotSpot commands by hand.
**Steps:**
1. Apply the **precision patch** (`%.2f` → `%.6f`, plan P0-4) and commit it as
   `patches/precision.patch`.
2. `run_hotspot.py`: give it a floorplan, power, config and options; it runs HotSpot in a fresh
   folder `data/<floorplan>/<run_id>/` and writes `meta.json` (config, seed, git commit).
3. `parse.py`: read `.steady`, `.ttrace` and `.grid.steady` into NumPy arrays, in a fixed block
   order.
4. `sweep.py`: run a list of jobs in parallel (one per CPU core), skipping finished ones (resume).
5. Time one HotSpot steady run and one transient step, for plan §1.4.
**Done when:** K can run a sweep of 100 jobs with one command.

### P0-4b. Infrastructure: floorplan and power generators (K)
**Goal:** write floorplans and power traces from code, reproducibly from a seed.
**Steps:**
1. `flpgen.py`: write `.flp` files from a Python description (list of named rectangles), and check
   that blocks don't overlap and that they tile the die.
2. `powergen.py`: (a) constant power vectors, random within each core type's range; (b) **phase
   traces**, where each core switches between idle/medium/busy levels with random phase lengths;
   (c) **calibration excitation traces** for T2 (A9.7: every core independent, phases from 1 ms to
   several seconds); (d) step inputs (1 W or 10 W in one block).
**Done when:** each generator gives the same output for the same seed.

### P0-5. Heterogeneous floorplans (K)
**Goal:** the chips we calibrate on.
**Concepts:** A6.
**Steps:**
1. Write HET-A (2 big, 4 little, L2, interconnect), HET-B (4 big, 4 little, GPU, L2, different
   layout) and HOM-16 (4×4).
2. Give each core type a power range (plan §4.2). Check the power density stays below ~3 W/mm².
3. Run each at full load (steady) and check peak temperatures land around 60–110 °C. Adjust
   ranges if not.
4. If the professor gives a floorplan, add it here.
**Done when:** the `.flp` files and a table of areas, power ranges, densities and full-load peaks.

## Phase P1: Calibration stage

### P1-1. Calibration by step runs: S1, T1, T3 (E)
**Goal:** the main calibration procedure: N runs → G, time constants and exponential weights.
**Concepts:** A7, A8.1, A9.1, A9.2.
**Steps:**
1. For each block j: transient run with a 10 W step in block j only (10 W, not 1 W, to beat
   rounding; divide by 10 afterwards thanks to linearity), starting from ambient, long enough to
   settle (≈ 5 × the sink's τ; check when it stops changing). Also a steady run for exact G.
2. **S1:** G column j = steady rise / 10.
3. **T1:** for each block, fit one time constant τ_i to its own step response.
4. **T3:** fit M shared τ's and the a_ijm weights to all curves at once (least squares; try
   M = 2…5). Constrain Σ_m a_ijm = G_ij.
5. Checks: G symmetric? Little cores have larger G_ii than big cores? τ's roughly ms / s / tens of
   s?
6. Record calibration cost: number of runs, total seconds.
**Done when:** model files for EV6, HET-A, HET-B, HOM-16; a heat map of G per floorplan; the fit
error on the calibration curves.

### P1-2. Calibration from one trace: ARX (T2) (K)
**Goal:** a cheaper calibration (one run instead of N) and how long the trace must be.
**Concepts:** A9.4, A9.6, A9.7.
**Steps:**
1. Generate excitation traces (P0-4b) of 1, 5, 20 and 60 s at Δt = 1 ms; run HotSpot on each.
2. Fit ARX by least squares for 1, 2 and 3 lags, with the steady gain forced to G (from P1-1).
3. Evaluate each fit in **transient (open-loop)** mode on a separate test trace.
**What you should see:** error falls as the trace gets longer and then flattens; more lags help
with the slow sink.
**Done when:** the plot "test error vs calibration trace length", one line per lag count.

### P1-3. Is per-floorplan calibration needed? (K)
**Goal:** justify the problem statement's "one-time per floorplan" calibration.
**Concepts:** A6, A8.1, A8.3.
**Steps:**
1. **Build S0:** make a large die with a tiny block in its centre, put 1 W there, run the grid model
   → the kernel. Write the power-blurring predictor (power map → FFT convolution with mirrored
   edges → average per block).
2. On HET-A and HET-B, compare on the same test power vectors:
   (a) S0 (no per-floorplan calibration);
   (b) **per-core-type model**: one self-heating value per core type and one shared coupling value
   (average the S1 values by type);
   (c) **transfer**: HET-A's coefficients used on HET-B for matching core types;
   (d) S1 calibrated on the floorplan itself.
**What you should see:** (a)–(c) clearly worse than (d), with the biggest errors for cores at
edges or next to the GPU.
**Done when:** a bar chart of MAE and T_peak error for (a)–(d), per floorplan.

## Phase P2: Predictor, steady state

### P2-1. Steady predictor: S0, S1, S2 (E)
**Goal:** the steady-state results table with all three metrics.
**Concepts:** A8, A11.
**Steps:**
1. 1,000 random power vectors per floorplan (within core-type ranges); HotSpot steady on each
   (the reference). For EV6 also gcc's average power.
2. Predict with S0, S1 and S2 (k = 2, 4, 8).
3. Accuracy: MAE, max error, T_peak error, hottest-core accuracy. Time: median µs per call.
   Size: bytes. Also HotSpot's time for the same inputs.
4. For S2's size story, also run on a 64-core floorplan.
**What you should see:** S1 essentially exact (≪ 0.01 K) in a few µs; S2 slightly worse, much
smaller at 64 cores; S0 1–3 K off.
**Done when:** the table, with rows in `summary.csv`.

## Phase P3: Predictor, transient

### P3-1. Transient simulation: T1, T2, T3 (E)
**Goal:** how well each model reproduces a whole HotSpot temperature trace from power alone.
**Concepts:** A9.2, A9.6 (open-loop mode), A11.
**Steps:**
1. Test traces: phase traces with seeds never used in calibration, 10–60 s long; gcc on EV6.
2. HotSpot transient on each (the reference), starting warm (from the steady state of the first
   power row).
3. Each model starts from the same initial condition and predicts the full trace, open loop.
4. Error over time, MAE, max error, T_peak error, µs per step, size.
**What you should see:** T3 close to exact; T2 close if well calibrated; T1 drifting on slow sink
effects.
**Done when:** plots of predicted vs HotSpot for one hot core, error-over-time plots, rows in
`summary.csv`.

### P3-2. Forecasting: error vs horizon (K)
**Goal:** how far ahead the predictor can be trusted. This feeds DTM (P6-2).
**Concepts:** A9.6 (forecast mode), A9.8.
**Steps:**
1. On the P3-1 test traces, at every step k, take HotSpot's temperature at k as the "sensor"
   reading.
2. Forecast k+1, k+10, k+100, k+1000 (1 ms … 1 s) with T0, T1, T2, T3, using the known planned
   power.
3. For T3, which has a hidden state, first update its state from the power history, then correct
   it so its output matches the sensor reading. Describe how you did this in the README.
**What you should see:** persistence fine at 1 ms and bad beyond; T3/T2 staying accurate much
longer.
**Done when:** the "error vs forecast horizon" plot.

### P3-3. Accuracy vs size vs time (Pareto) (K)
**Goal:** the main figure: all three required metrics in one picture.
**Concepts:** A11 (Pareto front), A8.2, A9.5.
**Steps:**
1. For each model, vary its size knob: M for T3, lags for T2, k for S2, r for T4 (if done).
2. Read all rows from `summary.csv`.
3. Plot error (y) vs model size (x), colour = prediction time; mark the Pareto front.
**Done when:** the figure, plus one sentence on which model `ltp` ships and why.

### P3-4. Exact state-space and balanced truncation: T4 ([OPT], E)
**Goal:** the exact reference, and the smallest model that is still accurate.
**Concepts:** A9.3, A9.5.
**Steps:**
1. Write a C helper linked to `libhotspot.a` that builds the block model and writes its internal
   conductance and capacitance matrices (4N + 12 nodes) to files.
2. In Python: matrix exponential → A, B at Δt; check it matches HotSpot's transient exactly.
3. Balanced truncation (e.g. `python-control` or SciPy) to r = 2…30; error vs r.
**Done when:** error vs r plot; T4 points added to P3-3.

## Phase P4: Robustness

### P4-1. Where does it break? (E)
**Goal:** test the calibrated predictor on inputs unlike its calibration.
**Concepts:** A9.7.
**Steps:** evaluate S1, T2 and T3 on (a) power 1.5× above the calibration range; (b) very bursty
traces (1 ms phases); (c) the same tasks **mapped onto different cores**; (d) a different Δt
(5 ms).
**What you should see:** S1/T3 unaffected (linearity); T2 possibly worse on inputs unlike its
calibration trace.
**Done when:** a robustness table, one column per case.

### P4-2. Recalibration after a package change ([OPT], K)
**Goal:** show that changing the heat sink invalidates the coefficients, and that recalibrating is
cheap. **Steps:** change `r_convec` (e.g. 0.1 → 0.3 K/W); evaluate old models (bad); rerun P1-1 and
P1-2 (good again); report recalibration time.

### P4-3. Leakage ([OPT], E)
**Goal:** what happens when HotSpot is no longer linear. **Concepts:** A10.
**Steps:** turn on `-leakage_used 1`; measure S1/T3 error; add the fixed-point leakage correction;
measure again.

## Phase P5: The product

### P5-1a. `ltp` package and commands (E)
**Goal:** usable tool. `ltp calibrate`, `ltp steady`, `ltp transient`, `ltp forecast`, with models
in `.npz`. A short README with one worked example. Wraps the model classes from J0.

### P5-1b. `ltp bench` and tests (K)
**Goal:** one command that prints accuracy, prediction time and model size for any model file
against stored HotSpot runs, and appends to `summary.csv`. Plus a few tests (e.g. S1 on a
calibration run reproduces it exactly). Final timings for the report are all taken with this on
**one** laptop.

## Phase P6: Wishlist, proactive DTM

### P6-1. Closed-loop HotSpot (E)
**Goal:** a "chip" that accepts new power every interval (A12, closed loop).
**Why it's needed:** normal HotSpot reads a whole power trace up front, and its transient output
keeps only block temperatures, so you can't pause, let a DTM policy change the power, and resume
exactly.
**Steps:** start from `HotSpot/sim-template.c` (it shows how to use HotSpot as a library). Build a
small program (or a Python extension) that keeps HotSpot's full internal state and, each interval,
takes a power vector and returns block temperatures (`compute_temp` once per step). Check it
matches a normal HotSpot run on the same trace.
**Done when:** a Python function `chip.step(P) -> T` that matches HotSpot.

### P6-2. Reactive vs proactive DTM (K)
**Goal:** the wishlist result: the predictor makes DTM better.
**Concepts:** A12, A9.8.
**Steps:**
1. HET-A, limit 85 °C, a workload that would overheat the big cores at full speed.
2. Policies, each deciding every 10 ms:
   - **No DTM** (to show the problem);
   - **Reactive:** sensor > limit → lower that core's DVFS level;
   - **Proactive (ltp):** `ltp.forecast` k steps ahead > limit → lower DVFS a step early, or
     migrate the task to a little core;
   - **Proactive with persistence** (a poor predictor) and **with an oracle** (HotSpot itself), to
     show that predictor quality is what matters.
3. Until P6-1 is ready, use T3 as a stand-in chip; then rerun with the real HotSpot stepper.
4. Metrics: peak T, time above limit, number of violations, performance proxy (A12), predictor
   µs per decision.
**What you should see:** proactive ltp ≈ oracle, both better than reactive in violations and lost
performance.
**Done when:** a table and a plot of a hot core's temperature under each policy.

### P6-3. Demo: which cores to switch on (E)
**Goal:** a simple decision made with the steady predictor.
**Steps:** on HET-A or HOM-16, choose which cores run a set of busy tasks; score *every* choice with
`ltp.steady` (S1) and with HotSpot; compare the coolest choice found by each and the total time.
**Done when:** "same best choice? yes/no; ltp took X ms, HotSpot took Y s".
