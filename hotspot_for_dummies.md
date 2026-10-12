# HotSpot for Dummies

Everything you need to know before starting this project, in plain language.
No prior knowledge assumed. Read top to bottom once, then use it as a glossary.

---

## Part 1: The big picture

### Why chips get hot
A processor is billions of tiny switches (transistors). Every time one switches, and even when
it is idle, it uses a little electrical energy, and **all of that energy ends up as heat**.
A laptop CPU turns about 15–45 W into heat; a desktop or server chip can turn 100–400 W into
heat. That heat leaves through an area roughly the size of a fingernail.

### Why heat is a problem
- **Correctness and speed:** hot transistors switch more slowly, so the chip has to run slower.
- **Lifetime:** heat speeds up wear-out (chips age faster).
- **Leakage:** hot transistors "leak" more current even when idle. More leakage means more heat,
  which means more leakage. This feedback loop can run away (*thermal runaway*).
- **Hard limit:** chips are typically allowed to reach about 85–105 °C. Above that they must throttle.

### What a "hot spot" is
Heat is not spread evenly. A small, very busy part of the chip (for example the register file,
which is read and written every cycle) can be **20–30 °C hotter** than a quiet part (like a big
cache). That small hot region is a **hot spot**. The *peak* temperature, not the average,
decides whether the chip must slow down. Our example1 run showed exactly this: the integer
register file reached about 70 °C while the L2 cache sat at about 51 °C on the same chip.

### Power vs power density (the most important idea)
- **Power** (watts, W) = how much heat per second.
- **Power density** (W/mm²) = how much heat per second *per unit area*.

Two blocks with the same power: the *smaller* one gets hotter, because its heat is squeezed
through a smaller area. In our EV6 example, the integer register file dissipates about
**2.9 W/mm²**, while the floating-point queue dissipates about **0.017 W/mm²**, a 170× difference.
That's why IntReg is the hot spot. When chips shrink each generation and power doesn't shrink as
fast, power density rises, and that's why heat is a central problem in chip design.

---

## Part 2: Heat flow explained with electricity

HotSpot's core trick is that **heat behaves like electricity**:

| Heat | Electricity |
|---|---|
| Temperature difference (°C or K) | Voltage (V) |
| Heat flow, i.e. power (W) | Current (A) |
| **Thermal resistance** (K/W): how hard it is for heat to get through | Resistance (Ω) |
| **Thermal capacitance** (J/K): how much heat a material soaks up before warming | Capacitance (F) |

So "Ohm's law for heat" is:

> **Temperature rise = Power × Thermal resistance**

**Example from our run:** the config has a heat-sink-to-air resistance `r_convec = 0.1 K/W`, and
the chip uses about 40 W. So the heat sink sits about 40 × 0.1 = **4 °C above the air**.
The output showed the heat-sink nodes about 6 °C above ambient (45 °C); the extra comes from
spreading inside the sink. Each further layer (spreader, interface material, silicon) adds its own
rise on top. Temperatures stack up like voltages along a chain of resistors.

**Resistance** decides the *final* temperature. **Capacitance** decides *how fast* you get there:
a big copper heat sink takes tens of seconds to warm up, while a thin silicon layer reacts in
milliseconds.

**Kelvin vs Celsius:** HotSpot works in Kelvin (K). A *difference* of 1 K equals a difference of 1 °C.
To convert a temperature: °C = K − 273.15. For example 318.15 K = 45 °C (HotSpot's default ambient).

---

## Part 3: The physical stack (what's between the chip and the air)

Looking at a packaged chip from the side (simplified; HotSpot models exactly these layers):

```
        air  (ambient, e.g. 45 °C inside a PC case)
   ┌────────────────────────────┐
   │        HEAT SINK (fins)    │  aluminium/copper, big, slow to heat up
   └────────────────────────────┘
       ┌────────────────────┐
       │   HEAT SPREADER    │      copper plate, spreads heat sideways
       └────────────────────┘
           ┌────────────┐
           │    TIM     │          thermal interface material ("thermal paste")
           ├────────────┤
           │ SILICON DIE│          the actual chip, where power is generated
           └────────────┘
       package substrate, solder balls, motherboard (the "secondary path", small)
```

- **Die:** the piece of silicon with the circuits. Typically 0.1–0.8 mm thick, 10–25 mm across.
- **TIM (Thermal Interface Material):** fills microscopic air gaps between die and spreader. Thin, but
  a poor conductor, so it often matters a lot.
- **Heat spreader:** spreads heat from the small die over a larger area.
- **Heat sink:** large finned metal block; a fan blows air across it.
- **Convection:** heat moving from the sink into the air. In HotSpot this is `r_convec`. A better
  fan means a lower `r_convec`.
- **Secondary path:** a little heat also escapes downward through the package to the motherboard.
  It's usually ignored (`-model_secondary 0`).
- **Lateral spreading:** heat moves sideways inside the silicon too. That's why a hot block next to
  cool blocks is cooler than one surrounded by other hot blocks. **This is the physics that makes
  floorplanning matter.**

---

## Part 4: Simulators

### What a "simulator" is
A program that predicts what a real system would do, so you don't have to build it. Measuring
temperature inside a real chip is hard (few sensors, poor resolution), and you can't build a new
chip to try an idea. So researchers simulate.

### Kinds of thermal simulators
- **Finite-element / CFD tools** (ANSYS Icepak, Cadence Celsius): very detailed, very accurate, slow
  (minutes to hours), and need a detailed 3D model. Used as "ground truth."
- **Compact thermal models** (HotSpot, 3D-ICE): turn the chip and package into a modest RC circuit.
  Fast (milliseconds to seconds), accurate to within a few degrees, and need only a floorplan and power.
  Ideal for early design and for running thousands of experiments.
- **ML surrogates:** neural networks trained on simulator outputs. Even faster, but only as good as
  their training data. This is the "lightweight predictor" direction.

### What HotSpot is
**HotSpot** is a free, open-source compact thermal simulator from the University of Virginia
(first released in 2003; we use the current GitHub release, which builds on version 6.0). You give it:
1. **where the blocks are** (floorplan),
2. **how much power each block uses** (power trace),
3. **what the package is made of** (config),

and it tells you **the temperature of every block** (or every grid cell) at steady state and over time.

It's "**pre-RTL**", meaning you can use it before the chip's circuits are designed, when you only
have a rough block layout and power estimates. That's early in design, when changing the layout
is still cheap.

### Other tools you'll see named
- **McPAT:** estimates the *power* of processor parts from activity counts.
- **CACTI:** estimates power, area and timing of caches and memories.
- **Sniper, gem5:** *performance* simulators. They run real programs on a simulated CPU and count
  activity.
- **The chain:** program → Sniper (activity) → McPAT (power) → HotSpot (temperature).
  **CoMeT**, Prof. Kedia's toolchain, automates this whole chain and feeds temperature back. We use
  only the last step, with given or synthetic power.
- **3D-ICE:** a HotSpot-like simulator from EPFL, strong on liquid cooling.

---

## Part 5: HotSpot's input files, one at a time

All dimensions are in **metres**. 0.001 m = 1 mm. Power is in **watts**.

### 5.1 Floorplan (`.flp`)
*A map of the chip: a list of rectangles.* One line per block:

```
<name>   <width>   <height>   <left-x>   <bottom-y>
```
Real lines from `ev6.flp` (a model of the Alpha 21264 processor, 16 mm × 16 mm):
```
L2        0.016000  0.009800  0.000000  0.000000    ← L2 cache: 16 mm wide, 9.8 mm tall, bottom-left corner
Icache    0.003100  0.002600  0.004900  0.009800    ← instruction cache: 3.1 × 2.6 mm, at x=4.9 mm, y=9.8 mm
Bpred_0   0.001033  0.000700  0.004900  0.012400    ← branch predictor (part 0)
```
- Origin (0,0) is the chip's bottom-left corner.
- Blocks are rectangles. Big blocks are sometimes split into parts (`_0`, `_1`) to get better
  accuracy.
- Blocks should tile the die without overlapping.
- **Changing this file is what "trying a different floorplan" means** in our project.

### 5.2 Power trace (`.ptrace`)
*How much power each block uses, over time.*
- First line: block names (must match the floorplan).
- Every following line: the power in watts of each block for one time step.
- Time step length = `sampling_intvl` in the config (0.01 s = 10 ms in the example).

```
L2_left  L2    L2_right  Icache  Dcache ...
1.44     7.37  1.44      8.27    14.3   ...    ← time step 1
0.963    4.92  0.963     5.4     8.91   ...    ← time step 2
```
`gcc.ptrace` has 100 rows (1 second) of power recorded while running the `gcc` compiler
benchmark. Total is about 40 W on average (38–59 W).
A constant trace (one row) is enough for a steady-state study.

### 5.3 Config (`.config`)
*The physics and package settings.* One `-option value` per line. The ones you'll actually touch:

| Option | Meaning | Example value |
|---|---|---|
| `-ambient` | air temperature (K) | 318.15 (= 45 °C) |
| `-r_convec` | heat sink → air resistance (K/W). Lower means a better fan | 0.1 |
| `-t_chip` | die thickness (m) | 0.00015 (0.15 mm) |
| `-t_interface`, `-k_interface` | TIM thickness and conductivity | 20 µm, 4 W/m·K |
| `-s_spreader`, `-t_spreader` | spreader side and thickness | 3 cm, 1 mm |
| `-s_sink`, `-t_sink` | heat sink side and thickness | 6 cm, 6.9 mm |
| `-sampling_intvl` | seconds per power-trace row | 0.01 |
| `-model_type` | `block` or `grid` (see Part 6) | block |
| `-grid_rows`, `-grid_cols` | grid resolution | 64 |
| `-leakage_used` | model the temperature → leakage loop | 0 |

Any config option can also be given on the command line, which overrides the file.

### 5.4 Materials (`.materials`)
Names and properties of materials (silicon, copper, water, ...): thermal conductivity and
heat capacity. It lets config and layer files say "silicon" instead of raw numbers.

### 5.5 Layer configuration (`.lcf`), only for 3D chips
Describes a *stack* of layers, from the bottom up. For each layer: its number, whether heat spreads
sideways in it, whether it produces power, its material properties, its thickness, and its own
floorplan file. From `example3/example.lcf`:
```
0  Y  Y  1.75e6  0.01  0.00015  floorplan1.flp    ← silicon die, makes power
1  Y  N  4e6     0.25  2.0e-05  floorplan1.flp    ← TIM/glue layer, no power
2  Y  Y  1.75e6  0.01  0.00015  floorplan2.flp    ← second silicon die, makes power
3  Y  N  4e6     0.25  2.0e-05  floorplan2.flp    ← TIM
```
(each value is actually on its own line in the real file.)

**Order matters:** layer 0 is the *bottom*, farthest from the heat sink. The *last* layer touches
the heat spreader. In `example4`, the hot core layer is deliberately placed second-to-last
("closer to the heat sink"), with only a TIM layer above it.

### 5.6 Floorplan description (`.desc`), only for HotFloorplan
Not a floorplan, but the *ingredients* for one: each block's area, allowed shapes (aspect-ratio
range), and which blocks talk to each other (wire density). HotFloorplan then *invents* a floorplan.

### 5.7 Initial temperatures (`.init`)
Starting temperature of every node for a transient run. Usually the steady-state result copied over.

---

## Part 6: How HotSpot computes, and its two models

### Steady state vs transient
- **Steady state:** "if this power stayed on forever, what temperature would everything settle at?"
  Just resistances. Fast.
- **Transient:** "how does temperature change over time as power changes?" Resistances plus
  capacitances, stepped through time.
- **Why the examples run steady state first, then transient:** the heat sink takes tens of
  seconds to warm up, but the trace is only 1 second long. Starting the transient from a cold
  chip would be unrealistic, so we start from the steady state (a "warmed-up" chip).

### Block model vs grid model
- **Block model:** one temperature per floorplan block (plus package nodes). Very fast (about
  0.01 s for us). Less accurate for big or long, thin blocks, because one number can't capture
  the variation inside them.
- **Grid model:** chops the die into an R×C grid (for example 64×64 cells) regardless of
  block shapes, and computes every cell. Slower (about 1 s at 64×64 on our machine). Gives a
  real *heat map*, and it's required for 3D stacks. A block's temperature is then the
  average/min/max/centre of its cells (`-grid_map_mode`).
- **Rule of thumb:** use the block model for big sweeps and the grid model for heat maps and 3D.

### SuperLU
A fast math library for solving the big system of equations in grid mode. We built HotSpot with it
(`make SUPERLU=1`). Without it, grid sizes must be powers of two (16, 32, 64, ...), and
microfluidic cooling doesn't run.

### Linearity (important for the predictor)
Without leakage, everything in HotSpot is linear: double every block's power and every temperature
*rise* above ambient doubles. Temperatures from two power patterns *add up* (superposition).
So for a fixed floorplan, HotSpot is really just a matrix: **T = T_ambient + R × P**.
Experiment E1 in the plan exploits this.

---

## Part 7: HotSpot's output files

| File | What's in it |
|---|---|
| `.steady` | Final temperature (K) of every node, one per line: `IntReg_0  342.43` |
| `.ttrace` | Transient: header of block names, then one row of temperatures (K) per time step |
| `.grid.steady` / `.grid.ttrace` | Grid model: temperature of every grid cell (per layer) |
| our `steady.csv`, `ttrace.csv`, `.png` | Our converted versions in °C, with plots |

**The strange extra names in `.steady`:**
- `iface_<block>`: the TIM layer directly above that block
- `hsp_<block>`: the heat spreader above that block
- `hsink_<block>`: the heat sink above that block
- `inode_N`: extra nodes for the parts of the spreader and sink that stick out beyond the die

You can see heat flowing upward: IntReg_0 342.4 K → iface 339.6 → hsp 327.2 → hsink 324.8 → air 318.15.
The **biggest drop is between silicon and spreader**. That's why the TIM matters.

---

## Part 8: Design and management vocabulary

- **Floorplan / floorplanning:** deciding where each block sits on the die. Traditional goals are small
  area and short wires. **Thermal-aware floorplanning** adds "keep hot blocks apart / near cool blocks."
- **Wire length:** blocks that communicate need wires. Longer wires mean slower and more power-hungry
  connections. Spreading hot blocks apart lengthens wires, so there's a **trade-off**.
- **HotFloorplan:** HotSpot's built-in floorplanner. Uses **simulated annealing**: start from a
  floorplan, make random changes, keep improvements, and *sometimes* keep worse ones early on
  (to escape local optima), gradually becoming pickier (cooling). It minimises
  `λA·area + λT·temperature + λW·wirelength`. The λ weights say how much you care about each.
- **Pareto front:** the set of designs where you can't improve one goal without worsening another.
- **DTM (Dynamic Thermal Management):** run-time reactions when the chip is too hot: slow the clock,
  lower the voltage, pause, or move work elsewhere.
- **DVFS (Dynamic Voltage and Frequency Scaling):** lowering voltage and frequency to cut power.
  This is the main DTM knob.
- **Throttling:** forcibly slowing down because of heat.
- **Task mapping / scheduling:** deciding which core runs which program. Thermally, spreading busy
  cores apart keeps peaks lower.
- **Dark silicon:** modern chips can't power all their transistors at once without overheating, so
  parts must stay off ("dark"). *Which* parts are on is a thermal decision.
- **Leakage power:** power used even when idle. It grows roughly exponentially with temperature,
  which creates the heat → leakage → heat loop.
- **Dynamic power:** power from switching activity. It depends on the workload.
- **Thermal time constant:** how quickly something heats up or cools down (resistance ×
  capacitance). Silicon reacts in milliseconds, heat sinks in tens of seconds.
- **Trace-based vs interval (co-)simulation:** *trace-based* means record power once, then compute
  temperature (what we do). *Interval/co-simulation* (CoMeT) means alternate performance, power and
  temperature every millisecond so temperature can change behaviour (for example via throttling).
  Trace-based is simpler but can't capture that feedback.

---

## Part 9: Beyond flat chips (2.5D, 3D, chiplets, liquid cooling)

- **2D chip:** one silicon die. The classic case.
- **Chiplets:** instead of one big die, several smaller dies, each doing a part of the job.
- **2.5D integration:** chiplets placed *side by side* on an **interposer** (a silicon or organic
  "mini circuit board" with dense wiring), all in one package. AMD and NVIDIA products do this.
  Thermal question: how far apart should chiplets be?
- **3D integration / 3D stacking:** dies stacked *on top* of each other, connected by **TSVs**
  (Through-Silicon Vias: vertical wires through the silicon). Example: 3D-stacked DRAM (HBM) or memory
  on top of logic. Thermal problem: only the top of the stack touches the heat sink, so heat from
  the bottom layers must travel through everything above. **The layer farthest from the sink tends
  to be the hottest.** This is a key finding in Prof. Kedia's CoMeT paper.
- **Microfluidic cooling:** tiny channels etched in or between dies, with liquid pumped through them.
  Very effective but complex. HotSpot can model it (`examples/example5`).

---

## Part 10: The ML / predictor vocabulary (for the last phase)

- **Surrogate model:** a fast model trained to imitate a slow simulator.
- **Dataset:** many (input, output) pairs, here (floorplan + power, temperatures) produced by running
  HotSpot many times.
- **Features:** numbers describing each input (block area, power density, distance to edge, neighbours' power).
- **Train / validation / test split:** learn on one part, tune on another, report on a third that the
  model never saw. **Generalisation** means doing well on genuinely new kinds of floorplans.
- **MAE / RMSE / max error (K):** average, root-mean-square, and worst-case prediction error.
- **CNN / U-Net:** neural networks for images; here, power-density map in → temperature map out.
- **Gradient boosting:** a strong, simple ML method for tabular features (e.g. XGBoost, LightGBM).
- **Superposition baseline:** for a fixed floorplan, the exact linear matrix trick from Part 6. An ML
  model should be compared against it.

---

## Part 11: How our setup fits together

```
 Windows (VS Code, your files)                     Ubuntu in WSL (where simulations run)
 ─────────────────────────────                     ─────────────────────────────────────
 Lightweight Thermal Predictor\                    ~/projects/HotSpot/
   *.md  (docs)                                      hotspot, hotfloorplan  (programs)
   analysis\  (our scripts)        ── copied ──▶     examples/  (inputs + outputs)
   results\   (CSVs, plots)        ◀── copied ──
   HotSpot\   (untouched original download)
```
- **WSL** = Windows Subsystem for Linux: a real Linux running inside Windows. HotSpot is Linux
  software, so it runs there.
- In File Explorer, the Linux files are at `\\wsl$\Ubuntu\home\ethan\projects\HotSpot`.
- Claude can run commands in WSL directly, so you don't have to type them.

## Part 12: A checklist before you start

You're ready when you can answer these without looking:

1. Why is IntReg the hottest block in the EV6 example, even though L2 uses more total power?
2. What does `r_convec` represent, and what happens to temperatures if you double it?
3. What's the difference between `.flp` and `.desc`?
4. When would you use the grid model instead of the block model?
5. Why run steady state before transient?
6. In a 3D stack, which layer would you expect to be hottest, and why?
7. What does thermal-aware floorplanning improve, and what does it *not* improve much?
8. Why is HotSpot "just a matrix" for a fixed floorplan, and when does that stop being true?

(Answers: 1. power *density*. 2. sink-to-air resistance; the rise above ambient goes up by about 2× for the convection part.
3. a real layout vs ingredients for a layout. 4. heat maps, big/thin blocks, 3D. 5. the heat sink is slow to warm.
6. the one farthest from the heat sink. 7. peak temperature and gradient; not average temperature.
8. linear RC network; breaks when the floorplan changes or leakage feedback is on.)
