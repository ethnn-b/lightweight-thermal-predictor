# Literature review: floorplan-level thermal simulation with HotSpot

Scope: work that uses or extends HotSpot to predict chip temperature from a floorplan and
power numbers, with emphasis on Prof. Rajesh Kedia's papers. It also covers the ML "fast
thermal predictor" line of work, since that is where a project called *Lightweight
Thermal Predictor* naturally ends up.

How to read this: each entry says what the paper did, and why it matters for *our* project.
Section 6 maps the papers onto the experiments in `plan.md`. Terms are explained in
`hotspot_for_dummies.md`.

Confidence notes: I read the CoMeT paper (arXiv version) and the HotFloorplan paper's first
pages in full. For the other papers I worked from abstracts, the authors' pages, the HotSpot
repository's own READMEs, and secondary summaries. Numbers marked *(abstract)* come from the
paper's abstract and I did not re-check them against the body.

---

## 1. HotSpot itself: where the tool comes from

### 1.1 Skadron et al., "Temperature-Aware Microarchitecture," ISCA 2003
K. Skadron, M. R. Stan, W. Huang, S. Velusamy, K. Sankaranarayanan, D. Tarjan.
Extended version: UVA Tech Report CS-2003-08.

- **Introduced HotSpot.** The paper's argument: temperature is a first-class design
  constraint, and architects need a thermal model that is fast enough to run alongside a
  performance simulator but still tracks *where* on the die heat builds up.
- **Key idea, the thermal–electrical analogy.** Heat flow behaves like current, temperature
  like voltage, thermal resistance like electrical resistance, and heat capacity like a
  capacitor. A chip and its package become an RC circuit that can be solved quickly.
- **Also introduced dynamic thermal management (DTM) evaluation**, for example throttling
  when a sensor reads too hot. This is the ancestor of the DTM work in Kedia's papers.
- **For us:** this is the citation for "why HotSpot," and the source of the EV6 (Alpha 21264)
  floorplan used in the examples.
- Source: cited in `HotSpot/README_archive/README-1.0` in this repository.

### 1.2 Huang et al., "HotSpot: A Compact Thermal Modeling Methodology for Early-Stage VLSI Design," IEEE TVLSI 14(5), 2006
W. Huang, S. Ghosh, S. Velusamy, K. Sankaranarayanan, K. Skadron, M. R. Stan.

- **The main HotSpot reference** to cite in any report.
- It models the full vertical stack: silicon die → thermal interface material (TIM) → heat
  spreader → heat sink → air. Lateral resistances model heat spreading sideways, and
  capacitances give transient (time-varying) behaviour.
- It targets **pre-RTL** design, meaning before the circuit is designed and when only a
  block-level floorplan and power estimates exist. The trade-off is accuracy versus speed:
  HotSpot is much faster than finite-element tools and gives up some accuracy.
- [Paper PDF (UVA)](https://www.cs.virginia.edu/~skadron/Papers/hotspot_tvlsi06.pdf)

### 1.3 Huang et al., "An Improved Block-Based Thermal Model in HotSpot 4.0 with Granularity Considerations," WDDD 2007
W. Huang, K. Sankaranarayanan, R. J. Ribando, M. R. Stan, K. Skadron.

- Shows that the **block model** (one temperature per block) loses accuracy when blocks are
  large or have extreme aspect ratios (long and thin). That motivated the **grid model**,
  which cuts the die into a uniform grid regardless of block shapes.
- **For us:** directly motivates Experiment B1 (block vs grid, and grid resolution).
- [Paper PDF](https://www.cs.virginia.edu/~skadron/Papers/wddd07-UVA-hotspot-final.pdf);
  also cited in `README-4.0`.

### 1.4 Huang et al., "Accurate, Pre-RTL Temperature-Aware Design Using a Parameterized, Geometric Thermal Model," IEEE Trans. Computers, 2008
- Validation of HotSpot against detailed finite-element simulation, plus design case studies.
- [Preprint](https://www.cs.virginia.edu/~skadron/Papers/hotspot_tc08_preprint.pdf)

### 1.5 Zhang, Stan, Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," UVA Tech Report CS-2015-04
- The version we are running. It adds three things relevant to us:
  1. **Calibration and validation** with IBM.
  2. **A fast direct solver (SuperLU).** The repo README says it is 10–100× faster for
     grid-mode steady state. We built HotSpot with it (`make SUPERLU=1`). Without it, grid
     sizes must be powers of two.
  3. **Heterogeneous 3D layers (`detailed_3D`)**, contributed by Ayse Coskun's group at Boston
     University. Different blocks in the same layer can have different materials. This is what
     makes 3D and 2.5D chiplet modelling possible.
- [Tech report PDF](https://www.cs.virginia.edu/~skadron/Papers/HotSpot60_TR.pdf);
  `HotSpot/README_archive/README-6.0`.
- The current GitHub release (the one we use) also adds **microfluidic (liquid) cooling**
  layers. See `examples/example5`.

---

## 2. Thermal-aware floorplanning (the most direct ancestor of our project)

### 2.1 Sankaranarayanan, Velusamy, Stan, Skadron, "A Case for Thermal-Aware Floorplanning at the Microarchitectural Level," J. Instruction-Level Parallelism 8, 2005
- **Question:** can *where you place blocks* reduce peak temperature, without touching power?
- **Why it can:** heat spreads sideways in silicon. A hot block surrounded by cool blocks
  can "borrow" their cooling capacity. A cluster of hot blocks cannot.
- **Method:** HotFloorplan, a simulated-annealing floorplanner (Wong–Liu slicing floorplans)
  whose cost function combines **area + temperature + wire length** (with weights λA, λT, λW).
  Wire length matters because moving blocks apart slows communication between them.
- **Result:** peak temperature fell by **about 20 °C on average and up to 35 °C**, with
  minimal performance loss, and the floorplanned designs needed no DTM at all.
- **Important caveat they state:** floorplanning does not reduce the *average* chip
  temperature much. It *evens out* the temperatures, so hot units get cooler and cool units
  get warmer.
- **For us:** HotFloorplan ships with HotSpot (`hotfloorplan`, `examples/example6`), and we
  have run it successfully. Experiments C3 and C4 replicate and extend this paper.
- [JILP PDF](https://www.jilp.org/vol7/v7paper15.pdf) (the PDF header says JILP 8, 2005)

### 2.2 Related floorplanning work (brief)
- Many follow-ups use simulated annealing or analytical placement with a HotSpot-style
  thermal term, for example temperature-aware floorplanning at UMN (ISLPED 2006) and 3D
  multi-core thermal floorplanning. They all rest on the same spreading argument.
- **TAP-2.5D** (Ma et al., DATE 2021, Boston University) applies the idea to **chiplets**
  on an interposer. It inserts *spacing* between chiplets to trade wire length for
  temperature, and uses HotSpot 6.0 for evaluation. The code is open
  ([GitHub](https://github.com/bu-icsg/TAP-2.5D), [paper](https://people.bu.edu/joshi/files/Ma_TAP-2.5D-DATE2021.pdf)).
  **ATPlace2.5D** (ICCAD 2024) later reports 5% lower peak temperature and 42% less wire
  length than TAP-2.5D *(abstract)*.
- **For us:** Experiment D2 (chiplet spacing) is a small-scale version of TAP-2.5D.

---

## 3. Prof. Rajesh Kedia's thermal work

Prof. Kedia (IIT Hyderabad CSE; PhD IIT Delhi, about 8.5 years at Texas Instruments) lists
*thermal management of processors and memories* as a current research focus. His thermal
papers come from the IIT Delhi group of Prof. Preeti Ranjan Panda, mostly with Lokesh Siddhu
as first author. The common thread: **3D-stacked memory gets hot, temperature and leakage
feed each other, and simulation infrastructure (built on HotSpot) is needed to study it.**
He also lists PhD and M.Tech students working on thermal management.
Sources: [homepage](https://people.iith.ac.in/rkedia/),
[publications](https://people.iith.ac.in/rkedia/publication.html).

### 3.1 CoMeT (ACM TACO 2022), the most relevant paper for us
L. Siddhu, **R. Kedia**, S. Pandey, M. Rapp, A. Pathania, J. Henkel, P. R. Panda.
"CoMeT: An Integrated Interval Thermal Simulation Toolchain for 2D, 2.5D, and 3D
Processor-Memory Systems." [arXiv 2109.12405](https://arxiv.org/abs/2109.12405),
[code](https://github.com/marg-tools/CoMeT) (MIT license).

What it is: a full toolchain in which a **performance simulator (Sniper)** runs a real program.
Every 1 ms "epoch", **McPAT** (cores) and **CACTI-3DD** (memory) turn activity counts into
power. **HotSpot** turns that power plus a floorplan into temperatures, and a **DTM policy**
can react by lowering frequency, for example, which changes performance. It closes the loop
that a plain power-trace → HotSpot run (what we are doing) leaves open.

Things in the paper that matter for our project:

- **Four core–memory arrangements** (their Fig. 2): *2D-ext* (core with separate DDR),
  *3D-ext* (core with separate 3D memory stack), *2.5D* (core and 3D memory side by side on
  an interposer), and *3D-stacked* (cores on top of memory).
- **floorplanlib**, a floorplan generator for regular grid layouts (cores, memory banks,
  layers, spacing). This is essentially what we need to build for synthetic floorplans.
- **HotSpot settings they used:** the grid model at **8×8** for the main runs and **32×32**
  for fine-grained per-core floorplans, with thermal simulation every 1 ms.
- **Leakage–temperature feedback:** memory leakage rises with temperature. At around 70 °C,
  leakage is about 40% of memory power. They fit an exponential curve and feed it back
  into HotSpot each epoch.
- **Findings we can reproduce in simplified form with HotSpot alone:**
  1. **The layer farthest from the heat sink is the hottest.** In 3D-stacked designs, the
     bottom memory layer, not the cores, becomes the system hot spot, even though the cores
     dissipate more power (their Figs. 10 and 15).
  2. **2.5D thermal coupling:** putting memory next to the cores raised core temperature by
     **up to 11 °C** for memory-heavy workloads compared with switching memory power off
     (their Fig. 14).
  3. **Within-core gradients:** with a fine-grained floorplan (ALU, FPU, register file, ROB
     and so on), execution units run hotter than caches (their Fig. 13). This is the same
     effect as IntReg being hottest in our EV6 run.
  4. **Thermal lag across layers:** after throttling, the core layer cools almost at once,
     but distant memory layers take several milliseconds. So a DTM policy that watches only
     the cores reacts too late (their Fig. 15).
- **Motivating point:** trace-based simulation (feed HotSpot a pre-recorded power trace,
  which is what we are doing) cannot capture feedback such as throttling or resource
  contention, and it *overestimated* temperature in their example. **This is a known
  limitation of our approach, and the report should say so.**

### 3.2 FastCool (DATE 2019), and "Leakage-Aware Dynamic Thermal Management of 3D Memories" (ACM TODAES 2020)
L. Siddhu, **R. Kedia**, P. R. Panda.
- Temperature raises leakage, which raises temperature: a positive feedback loop. In
  3D memories the fix is to **shut off hot memory channels**, after first moving their data
  to 2D memory.
- DATE version: **27% average runtime improvement (up to 66%)** over policies that reduce only
  dynamic power *(abstract)*. The journal version adds **EEFC** (energy-efficient FastCool),
  which picks channels to close based on temperature, leakage, access rate and *position*.
- **For us:** the leakage loop is Experiment D4. HotSpot has a `-leakage_used` option, or we
  can iterate in Python.
- [DATE 2019 PDF](https://www.cse.iitd.ac.in/~siddhulokesh/papers/FastCool_DATE2019.pdf),
  [TODAES](https://dl.acm.org/doi/abs/10.1145/3419468)

### 3.3 CoreMemDTM (DATE 2022, best paper nomination)
L. Siddhu, **R. Kedia**, P. R. Panda. "Integrated Processor Core and 3D Memory Dynamic Thermal
Management for Improved Performance." Manages core and memory temperature *together* rather
than separately. I could not find the full abstract online, so this summary rests on the title
and how CoMeT discusses it.

### 3.4 "Dynamic Thermal Management of 3D Memory through Rotating Low Power States and Partial Channel Closure" (ACM TECS 2023)
L. Siddhu, A. Bagchi, **R. Kedia**, I. Ahmad, S. Pandey, P. R. Panda.
Rotates which memory parts are in low-power states so heat does not concentrate. Related
Indian patents (2021) cover thermal management of 3D storage by low-power states.
[ACM](https://dl.acm.org/doi/10.1145/3624581)

### 3.5 HotSniper (the toolchain CoMeT extends)
Pathania and Henkel, ESL 2018. Sniper plus McPAT plus HotSpot for many-core interval thermal
simulation (cores only). CoMeT adds memory at about 5% extra simulation time. HotSniper is by
Pathania and Henkel, so Kedia's link to it is through CoMeT.

**Takeaway for the course:** Prof. Kedia's work consistently uses HotSpot as the thermal engine
inside a bigger loop, and cares about (a) 3D/2.5D stacks, (b) memory as well as cores,
(c) leakage feedback, and (d) DTM policies. A project that studies **floorplan and stack
geometry → temperature** with HotSpot fits squarely in that line. Adding a small version of
one of (a)–(d) would connect it directly to his research.

---

## 4. Fast / "lightweight" thermal predictors (ML surrogates)

Motivation: HotSpot is fast (milliseconds for the block model, about 1 s for a 64×64 grid on
our machine), but design-space exploration and run-time management can need millions of
evaluations. Several groups train a model on simulator outputs to predict temperature
faster still.

| Work | Idea | Data source | Reported result |
|---|---|---|---|
| **ThermEDGe** (Chhabria et al., ASP-DAC 2021) | CNN encoder–decoder: power map image → temperature map image | Commercial-style thermal solver | About 0.6% average error, millisecond inference *(abstract)*. [arXiv](https://arxiv.org/abs/2009.09009), [code](https://github.com/VidyaChhabria/ThermEDGe-and-IREDGe) |
| **GCN for chiplets** (Chen, Jin, Tan, ASP-DAC 2022) | Graph neural network on the thermal-resistance graph | HotSpot | RMSE 0.31 K; 2.6× faster than HotSpot + SuperLU; generalises to unseen designs at < 0.67 K *(abstract)* |
| **DeepOHeat** (Liu et al., DAC 2023) | Physics-informed operator learning (DeepONet), can train without labelled data | Cadence Celsius 3D | 1000×–300000× speed-up on unseen cases *(abstract)*. [code](https://github.com/Cadence-Celsius/DeepOHeat) |
| **IC-ThermBench** (arXiv 2608.23977, 2026) | Open benchmark for learned 2.5D/3D thermal prediction | **HotSpot** grid model, 64×64, detailed 3D | Within a design family, RMSE about 0.4–0.9 K. On *new* package types, zero-shot error explodes to about 15 K and 10 labelled samples bring it to about 2 K. [arXiv](https://arxiv.org/html/2608.23977) |

Lessons for us:

1. **HotSpot is the standard data generator** for this kind of work (GCN paper, IC-ThermBench),
   so a HotSpot-generated dataset is a legitimate course-project contribution.
2. **Generalization is the hard part.** Models trained on one family of floorplans fail on
   different ones. Train/test splits must be designed carefully (Experiment E3).
3. **A physics baseline is cheap and strong.** Without leakage, HotSpot's model is
   *linear*: temperature rise = (thermal resistance matrix) × (power vector). For a *fixed*
   floorplan, that matrix can be measured with one simulation per block and then predicts
   *any* power trace exactly in microseconds. An ML model must beat this baseline where
   it applies, which is across *different* floorplans (Experiment E1). Most ML papers above do
   not report such a baseline. This is an easy and honest contribution for us.

---

## 5. Other simulators you will see cited

- **3D-ICE** (EPFL): thermal simulator with microchannel liquid cooling for 3D ICs (v4.0, 2025,
  adds heterogeneous chiplets). Similar inputs and outputs to HotSpot.
- **McPAT / CACTI**: power, area and timing models for cores and memory. They generate the
  *power* numbers HotSpot needs.
- **Sniper / gem5**: performance simulators that produce the activity counts McPAT converts
  to power.
- **ANSYS Icepak, Cadence Celsius**: commercial detailed (finite-element/CFD) thermal tools,
  the "ground truth" HotSpot is validated against.

---

## 6. Gaps a course project can fill (and which plan.md experiments address them)

| Gap or opportunity in the literature | Our experiment |
|---|---|
| Few papers show a systematic, beginner-reproducible study of *which floorplan features* drive peak temperature (power density, adjacency, edge placement, aspect ratio) | B2, C1, C2 |
| HotFloorplan's area / wire length / temperature trade-off is rarely re-examined as a Pareto front | C3, C4 |
| CoMeT's 3D finding (far layer is hottest) shown with a full toolchain; can it be reproduced with HotSpot alone and synthetic stacks? | D1 |
| Chiplet spacing (TAP-2.5D) as a simple parameter sweep | D2 |
| ML thermal predictors rarely compare against the exact linear (superposition) baseline | E1, E2 |
| Generalization of learned predictors to unseen floorplan families | E3 |

---

## References (compact list)

1. K. Skadron et al., "Temperature-Aware Microarchitecture," ISCA 2003.
2. W. Huang et al., "HotSpot: A Compact Thermal Modeling Methodology for Early-Stage VLSI Design," IEEE TVLSI 14(5):501–513, 2006.
3. W. Huang et al., "An Improved Block-Based Thermal Model in HotSpot 4.0 with Granularity Considerations," WDDD 2007.
4. W. Huang et al., "Accurate, Pre-RTL Temperature-Aware Design Using a Parameterized, Geometric Thermal Model," IEEE Trans. Computers, 2008.
5. R. Zhang, M. R. Stan, K. Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," UVA TR CS-2015-04, 2015.
6. K. Sankaranarayanan, S. Velusamy, M. R. Stan, K. Skadron, "A Case for Thermal-Aware Floorplanning at the Microarchitectural Level," JILP 8, 2005.
7. Y. Ma et al., "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems," DATE 2021.
8. L. Siddhu, R. Kedia, S. Pandey, M. Rapp, A. Pathania, J. Henkel, P. R. Panda, "CoMeT: An Integrated Interval Thermal Simulation Toolchain for 2D, 2.5D, and 3D Processor-Memory Systems," ACM TACO, 2022.
9. L. Siddhu, R. Kedia, P. R. Panda, "FastCool: Leakage Aware Dynamic Thermal Management of 3D Memories," DATE 2019; journal version ACM TODAES 26(2), 2020.
10. L. Siddhu, R. Kedia, P. R. Panda, "CoreMemDTM: Integrated Processor Core and 3D Memory Dynamic Thermal Management for Improved Performance," DATE 2022.
11. L. Siddhu, A. Bagchi, R. Kedia, I. Ahmad, S. Pandey, P. R. Panda, "Dynamic Thermal Management of 3D Memory through Rotating Low Power States and Partial Channel Closure," ACM TECS, 2023.
12. A. Pathania, J. Henkel, "HotSniper: Sniper-Based Toolchain for Many-Core Thermal Simulations in Open Systems," IEEE ESL, 2018.
13. V. A. Chhabria et al., "Thermal and IR Drop Analysis Using Convolutional Encoder-Decoder Networks," ASP-DAC 2021.
14. L. Chen, W. Jin, S. X.-D. Tan, "Fast Thermal Analysis for Chiplet Design based on Graph Convolution Networks," ASP-DAC 2022.
15. Z. Liu et al., "DeepOHeat: Operator Learning-based Ultra-fast Thermal Simulation in 3D-IC Design," DAC 2023.
16. IC-ThermBench: An Open, Progressive Benchmark for Generalizable 2.5D/3D-IC Thermal Learning, arXiv 2608.23977, 2026.
