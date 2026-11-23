# Literature review and references

One document with two parts:

- **Part A** is the literature review: what each related work did and what it means for our
  project, the gaps it leaves, and a compact reference list.
- **Part B** maps every source onto the models and claims in this project (HotSpot linearity,
  S0/S1/S2, T1–T4, leakage, comparisons, data, software), with a trust tag on each entry. It also
  gives the calibration time of each model (B9) and ends with a gaps checklist (B10).

Terms are explained in `hotspot_for_dummies.md`; the experiment plan is `plan.md`.

---

# Part A: Literature review: lightweight chip temperature prediction (with HotSpot as ground truth)

Scope: methods that predict chip temperature much faster than a full thermal simulation,
for use at design time (inside a floorplanner) or at run time (inside a thermal manager or
workload mapper). HotSpot appears here as the reference simulator and data generator, not as
the subject. Prof. Rajesh Kedia's thermal work is covered in §6, as the run-time context the
predictor serves.

How to read this: each entry says what the work did and what it means for *our* project.
§7 maps gaps in the literature onto the experiments in `plan.md`. Terms are explained in
`hotspot_for_dummies.md`.

**Confidence notes.** I read CoMeT (arXiv) and the HotFloorplan paper's first pages in full, and
the IC-ThermBench HTML version in part. For the other papers I worked from abstracts, author
pages, the HotSpot repository's READMEs, and search-engine summaries. Numbers marked
*(abstract)* come from an abstract and were not checked against the paper body. Check the
primary source before quoting any number in the report.

---

## 1. What is a "lightweight temperature predictor"?

The literature uses the phrase for two different jobs. Our plan calls them mode R and mode D:

| | **Run-time (mode R)** | **Design-time (mode D)** |
|---|---|---|
| Question | How hot will each core be in the next few ms, given what I plan to run? | How hot will this *layout* get? |
| Fixed | Chip and floorplan | Package |
| Varies | Power over time | Floorplan and power |
| Users | DTM, OS scheduler, workload mapper | Floorplanner, placer, design-space exploration |
| Typical methods | RC/state-space models, system identification, ARMA, small regressors | Convolution kernels, CNN/U-Net, graph networks, neural operators |
| Main constraint | Microseconds and kilobytes, on the chip | Thousands of evaluations per second, accurate on unseen layouts |

Methods also fall into three families, from most to least physics:

1. **Physics-derived:** start from the same RC network HotSpot uses and make it cheaper
   (superposition, matrix exponentials, model-order reduction, Green's-function convolution). §3.
2. **Identified / time-series:** fit a small model to observed temperatures, with or without
   power as input. §4.
3. **Learned surrogates:** train a neural network on many simulator runs. §5.

A recurring theme is that each family's papers rarely compare against the others. Our project
puts all three on the same data (§7).

---

## 2. The ground truth: HotSpot

### 2.1 Skadron et al., "Temperature-Aware Microarchitecture," ISCA 2003
Introduced HotSpot and the thermal–electrical analogy (heat = current, temperature = voltage,
thermal resistance and capacitance = R and C). It also introduced the evaluation of dynamic
thermal management (DTM). Source of the EV6 floorplan used in our examples.

### 2.2 Huang et al., "HotSpot: A Compact Thermal Modeling Methodology for Early-Stage VLSI Design," IEEE TVLSI 14(5), 2006
The main HotSpot reference. Models die → TIM → spreader → sink → air as an RC network with
lateral resistances. Targets pre-RTL design, trading some accuracy for speed against
finite-element tools. **For us:** because HotSpot *is* a linear RC network (without leakage),
the predictor can recover it exactly for a fixed floorplan (§3).
[PDF](https://www.cs.virginia.edu/~skadron/Papers/hotspot_tvlsi06.pdf)

### 2.3 Huang et al., WDDD 2007 (HotSpot 4.0 granularity) and IEEE Trans. Computers 2008 (validation)
The block model loses accuracy for large or long, thin blocks, which motivated the grid model.
The 2008 paper validates HotSpot against finite-element simulation. **For us:** P0-3 picks the
ground-truth resolution, and these papers bound how much HotSpot itself can be trusted
(roughly 1–2 °C against detailed tools).
[WDDD PDF](https://www.cs.virginia.edu/~skadron/Papers/wddd07-UVA-hotspot-final.pdf),
[TC preprint](https://www.cs.virginia.edu/~skadron/Papers/hotspot_tc08_preprint.pdf)

### 2.4 Zhang, Stan, Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," UVA TR CS-2015-04
The version we run: IBM calibration, a SuperLU direct solver (10–100× faster grid steady state),
and heterogeneous 3D layers. The GitHub release adds microfluidic cooling.
[PDF](https://www.cs.virginia.edu/~skadron/Papers/HotSpot60_TR.pdf)

**HotSpot is the standard data generator in this field.** The chiplet GCN (§5.2), the
2025 multi-core GCN line (§5.3) and IC-ThermBench (§5.6) all generate labels with HotSpot, so a
HotSpot-trained predictor is a legitimate design, as long as the report says it predicts
*HotSpot*, not silicon.

---

## 3. Physics-derived fast predictors

### 3.1 Superposition and the thermal influence matrix
Without leakage, HotSpot's steady state is T = T_amb + R·P, where R is an N×N matrix. Run the
simulator N times with 1 W in one block each and R is known exactly; after that every
prediction is one matrix–vector product. This is standard linear-systems reasoning and is
used implicitly in many thermal-aware mapping papers. **For us:** model R1, the exact
fixed-floorplan baseline that any learned model must beat.

### 3.2 MatEx: Pagani, Chen, Shafique, Henkel, DATE 2015
"MatEx: Efficient Transient and Peak Temperature Computation for Compact Thermal Models."
- For any compact thermal model written as first-order ODEs (C·dT/dt = −G·T + P, exactly
  HotSpot's form), solves the transient analytically with **matrix exponentials** instead of
  time-stepping, and finds *transient peaks* in a few milliseconds, which is fast enough for
  run-time use *(abstract)*. Open-source tool from KIT.
- A later paper notes that MatEx's cost grows quickly with the number of thermal nodes and
  schedule intervals, so it suits small systems (secondary source).
- **For us:** the basis of the optional exact state-space model R4 (P1-3). Model-order
  reduction addresses the scaling limitation.
- [PDF](https://cesdownloads.itec.kit.edu/pdf/pagani/Pagani-DATE-2015-MatEx.pdf)

### 3.3 Model-order reduction and Kalman estimation: Sharifi, Liu, Rosing, ISQED 2008; Sharifi & Rosing, IEEE TCAD 2010
"Accurate Temperature Estimation for Efficient Thermal Management" (ISQED 2008) and
"Accurate Direct and Indirect On-Chip Temperature Sensing for Efficient DTM" (TCAD 2010).
- A Kalman filter on a thermal RC model estimates temperatures at locations with no sensor and
  removes sensor noise. A precomputed steady-state Kalman gain keeps it cheap enough for run
  time.
- Related work (e.g. a 2018 *Sensors* paper on noisy thermal sensors) reduces the RC model by
  projection-based model-order reduction before using it in the Kalman prediction step.
- **For us:** background for the reduced state-space in optional experiment P1-3.
- [ISQED PDF](https://cseweb.ucsd.edu//~shsharif/papers/sharifi_isqed08.pdf)

### 3.4 Power blurring: Ziabari, Park, Ardestani, Renau, Kang, Shakouri, IEEE TVLSI 22(11), 2014
"Power Blurring: Fast Static and Transient Thermal Analysis Method for Packaged Integrated
Circuits and Power Devices."
- Computes a temperature map by **convolving the power map with a thermal "blur" kernel**
  (the response to a point heat source), like blurring an image. Handles the chip's finite
  size and boundaries, and 3D spreading in the sink. Works for steady state and transients.
- Validated against a commercial FEM tool and against HotSpot; a citing source says it beats
  HotSpot by an order of magnitude in speed and accuracy (secondary source).
- **For us:** model D1, the physics baseline for *new* floorplans, built from a handful of
  HotSpot impulse runs and needing no training set. It is also the "physics" half of the
  hybrid D3b.
- [PDF (UCSC)](https://users.soe.ucsc.edu/~renau/docs/tvlsi13.pdf)

---

## 4. Run-time temperature predictors (mode R)

### 4.1 Coskun, Rosing, Gross, "Utilizing Predictors for Efficient Thermal Management in Multiprocessor SoCs," IEEE TCAD 2009
- Forecasts each core's temperature with an **ARMA** model fitted to its recent temperature
  readings. Workloads have stationary phases, so regressing on past readings works. A
  sequential probability ratio test (SPRT) detects phase changes and triggers re-fitting.
- Proactive management using the forecasts gives **60% fewer hot spots, 80% smaller spatial
  gradients and 75% fewer thermal cycles** than reactive management on an UltraSPARC T1
  *(abstract)*.
- **For us:** model R2 (temperature-only AR forecaster, a simpler form of ARMA). Its weakness,
  that it can't see power changes coming, is what P1-2 tests against the power-aware ARX (R3).
- [PDF](http://varys.ucsd.edu/media/papers/coskun2009utilizing.pdf)

### 4.2 Yeo, Liu, Kim, "Predictive Dynamic Thermal Management for Multicore Systems," DAC 2008
- Two models: an *application-based* model that learns each program's thermal behaviour, and a
  *core-based* model that estimates a core's temperature from steady-state temperature and
  workload. About **1.6% average prediction error** *(abstract)*.
- Used to migrate a thread from an overheating core to the coolest *predicted* core; on an
  Intel quad-core, ≈5 °C lower peak with < 1% performance loss *(abstract)*.
- **For us:** the closest ancestor of Demo 1 (predictor inside a mapper).

### 4.3 Zhang, Guliani, Ogrenci-Memik, Memik, Yoshii, Sankaran, Beckman, "Machine Learning-Based Temperature Prediction for Runtime Thermal Management Across System Components," IEEE TPDS 29(2), 2018
- Builds **lightweight** predictors (Gaussian process, neural network, Lasso linear regression)
  for run-time management, using feature selection to cut cost. Average errors: GP 4.2 → 2.9 °C
  after optimisation, NN 2.9 °C, Lasso 3.8 °C *(abstract)*.
- Model-guided task placement lowered average system temperature by up to **11.9 °C**, and
  migration cut cooling power by ≈17% on a 16-node system *(abstract)*.
- **For us:** shows that in the run-time setting, simple linear and small models are the
  norm, and that "lightweight" is judged by deployment cost. Their errors (≈3 °C on real
  hardware) are much larger than what we can reach against a simulator, and the report should
  say why: real sensors, unknown power, and unmodelled physics.
- [Author page](https://akhilguliani.github.io/publication/mlThermal/), [OSTI](https://www.osti.gov/pages/biblio/1461523)

### 4.4 Mobile platforms: Singla, Kaur, Unver, Ogras (DATE 2015); Bhat, Gumussoy, Ogras (TVLSI 2017/2018)
Predictive thermal and power management on real phones/boards (Odroid-XU3, Snapdragon 810):
identify a power-to-temperature model online, predict where temperature will be, and act before
the limit. **For us:** evidence that *identified* low-order models (our ARX model, R3) are what is
actually deployed on real devices.
[arXiv (power–temperature dynamics)](https://arxiv.org/pdf/2003.11081)

### 4.5 Post-silicon full-chip maps: RealMaps (Sadiqbatcha, Zhang, Amrouch, Tan, IEEE TC 2021) and TherMapNet (arXiv 2608.21887, 2026)
- **RealMaps** estimates full-chip heat maps in real time on commercial CPUs from on-chip
  sensors and utilisation, trained on infrared images: 0.9 and 1.2 °C RMSE on two chips,
  0.4 ms per inference *(abstract)*.
- **TherMapNet** (Gu et al., submitted to ICCD 2026): Transformer over performance-counter time
  series + attention CNN → full-chip map, with no power estimation step. RMSE < 0.26 °C,
  < 2.4 ms on an RTX 3090 *(abstract)*. The ground-truth source isn't stated in the abstract.
- **For us:** context only. These works run on GPUs or need IR cameras for training, so they
  are much heavier than what we target.
- [RealMaps (NSF PAR)](https://par.nsf.gov/biblio/10324767), [TherMapNet](https://arxiv.org/abs/2608.21887)

---

## 5. Learned surrogates across designs (mode D)

### 5.1 ThermEDGe: Chhabria et al., ASP-DAC 2021
CNN encoder–decoder: power-map image → temperature-map image. About 0.6% average error, with
millisecond inference *(abstract)*. Open code.
**For us:** model D3 (small U-Net).
[arXiv](https://arxiv.org/abs/2009.09009), [code](https://github.com/VidyaChhabria/ThermEDGe-and-IREDGe)

### 5.2 Graph networks for chiplets: Chen, Jin, Tan, ASP-DAC 2022
GCN over the thermal-resistance graph, **trained on HotSpot**. RMSE 0.31 K, 2.6× faster than
HotSpot + SuperLU, < 0.67 K on unseen designs *(abstract)*. Citing papers also describe a
graph-attention variant by the same line of work, trained on HotSpot data.
**For us:** confirms HotSpot as a data source. Note the modest **2.6× speed-up**: once HotSpot
uses SuperLU, a neural network is not automatically much faster, which is why we time
everything (plan §6).

### 5.3 "Real-Time Temperature Prediction for Large-Scale Multi-Core Chips Based on Graph Convolutional Neural Networks," *Electronics* 14(6):1223, 2025
GCN for many-core chips, < 2 ms per inference, at least 10× faster than HotSpot; its
comparison table lists memory 120 MB (HotSpot) vs 17.45 MB (MatEx) vs 5.53 MB (GCN), and
complexity O(N³), O(WN²), O(|E|f) respectively (search summary; full text not accessed).
**For us:** one of the few papers that compares memory footprint and against MatEx; a model
for our four-cost reporting.
[DOI](https://doi.org/10.3390/electronics14061223)

### 5.4 DeepOHeat: Liu et al., DAC 2023
Physics-informed operator learning (DeepONet) for 3D-IC thermal simulation; can train from the
heat equation without labelled data. 1000×–300000× speed-ups on unseen cases *(abstract)*.
[code](https://github.com/Cadence-Celsius/DeepOHeat)

### 5.5 ThePlace: Liu, Liu, Yu, Chen, Xu, ASP-DAC 2025
"Thermal-Aware Placement With Operator Learning-Based Ultra-Fast Simulator." A **Fourier
neural operator** solves steady-state heat conduction and is used *inside* a force-directed
placer that trades peak temperature against wire length; compared with DREAMPlace it reports a
significant temperature reduction with little wire-length change *(abstract)*.
**For us:** a full-scale version of what Demo 2 shows (a predictor guiding layout choices). It shows the
design-time predictor's value is measured by the layouts it leads to, not only its error.
[PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C246-ASPDAC2025-ThePlace.pdf)

### 5.6 IC-ThermBench: Huang, Yang, Ding, Xin, arXiv 2608.23977, Aug 2026
"An Open, Progressive Benchmark for Generalizable 2.5D/3D-IC Thermal Learning."
- Labels from **HotSpot**, grid-based detailed-3D flow, **64×64**, steady state (scopes S2–S5).
- Eight baselines: U-Net, FNO, U-FNO, SAU-FNO, DeepOHeat, and three sizes of **Therm-FM**
  (a thermal "foundation model", arXiv 2605.22663).
- Five *generalisation scopes*. Best results in the HTML version: layout variation (S2) RMSE
  0.44 K; material variation (S3) 0.72 K; boundary-condition variation (S4) 0.93 K; **unseen
  package (S5) zero-shot ≈ 15.5 K RMSE**. With 10 labelled samples per new case, MAE falls by
  ≈67–90%, best 2.25 K. (The arXiv abstract gives slightly different figures, S4 RMSE 1.216 K,
  S5 15.99 K, 10-shot 2.60 K, presumably from a different version. Quote one version
  consistently.)
- **For us:** the most directly comparable recent work: same simulator, same resolution, same
  question. It sets a realistic accuracy target (≈ 0.5–1 K within family) and confirms that
  **generalisation to new packages is the open problem**, which is exactly P3-1. It does not
  include a physics baseline such as power blurring or the influence matrix.
- [arXiv](https://arxiv.org/abs/2608.23977), [HTML](https://arxiv.org/html/2608.23977)

---

## 6. Where the predictor gets used

### 6.1 Thermal-aware floorplanning (where mode D is used)
- **Sankaranarayanan, Velusamy, Stan, Skadron, "A Case for Thermal-Aware Floorplanning at the
  Microarchitectural Level," JILP 2005.** HotFloorplan: simulated annealing minimising
  λA·area + λT·temperature + λW·wire length. Peak temperature fell by about 20 °C on average
  (up to 35 °C); average temperature barely changes, since heat is redistributed.
  The temperature term is evaluated thousands of times per run, which is exactly where a fast
  predictor pays off. **For us:** HotFloorplan ships with HotSpot; we use its outputs as a
  realistic held-out test family and as the comparison point for Demo 2.
  [PDF](https://www.jilp.org/vol7/v7paper15.pdf)
- **TAP-2.5D** (Ma et al., DATE 2021) inserts spacing between chiplets to trade wire length for
  temperature, using HotSpot 6.0 for evaluation; **ATPlace2.5D** (ICCAD 2024) improves on it
  *(abstract)*. **For us:** the optional chiplet test family.
  [code](https://github.com/bu-icsg/TAP-2.5D)

### 6.2 Run-time thermal management and Prof. Kedia's work (where mode R is used)
Prof. Kedia (IIT Hyderabad CSE) lists thermal management of processors and memories as a
current focus. His thermal papers come from Prof. P. R. Panda's group at IIT Delhi, mostly with
Lokesh Siddhu as first author. I found no paper of his specifically on temperature
*prediction*. The link to our project is that his DTM work needs fast temperature estimates
inside a control loop.
Sources: [homepage](https://people.iith.ac.in/rkedia/), [publications](https://people.iith.ac.in/rkedia/publication.html).

- **CoMeT** (Siddhu, Kedia, Pandey, Rapp, Pathania, Henkel, Panda; ACM TACO 2022).
  Sniper + McPAT + CACTI-3DD + **HotSpot** every **1 ms**, with a DTM policy closing the loop;
  2D, 2.5D and 3D core–memory systems. Grid model at 8×8 (32×32 for fine floorplans). Findings:
  the layer farthest from the sink is hottest in 3D stacks; 2.5D memory raises core temperature
  by up to 11 °C; distant layers lag after throttling.
  **For us:** (1) sets the 1 ms interval for mode R; (2) HotSpot is called every epoch, so a
  faster predictor directly speeds up such toolchains; (3) the thermal-lag observation is
  a reason a predictor must capture slow as well as fast heating; (4) its point that trace-based simulation
  misses feedback is a limitation the report must state, and the optional closed-loop demo (P4-4) addresses it
  in part.
  [arXiv 2109.12405](https://arxiv.org/abs/2109.12405), [code](https://github.com/marg-tools/CoMeT)
- **FastCool** (DATE 2019) and its journal version (ACM TODAES 2020): leakage–temperature
  feedback in 3D memories; close hot channels. 27% average runtime improvement *(abstract)*.
  **For us:** P3-3, where leakage breaks linear predictors.
  [PDF](https://www.cse.iitd.ac.in/~siddhulokesh/papers/FastCool_DATE2019.pdf)
- **CoreMemDTM** (DATE 2022): joint core and 3D-memory DTM. **Rotating low-power states**
  (ACM TECS 2023): spreads memory heat over time. Both are policies that would consume a
  run-time predictor.
- **HotSniper** (Pathania & Henkel, ESL 2018): the Sniper + HotSpot toolchain CoMeT extends.

---

## 7. Gaps a course project can fill, and where plan.md addresses them

| Gap in the literature | Our experiment |
|---|---|
| Learned predictors are rarely compared against the **exact linear baseline** (influence matrix). IC-ThermBench includes no physics baseline | P1-1, P2-2; every results table |
| "Lightweight" is claimed but accuracy, speed, size and build cost are seldom reported together | Plan §1.3 targets; P2-4 results table |
| Physics-based, identified and temperature-only run-time models are rarely evaluated **on the same traces** | P1-2 (error vs horizon for R0–R3) |
| Generalisation to unseen floorplans and packages is the open problem (IC-ThermBench S5) | P3-1, and the physics-hybrid D3b |
| Predictor quality is usually judged by error, rarely by **whether it leads to the same decisions** | P4-2 (mapping), P4-3 (floorplan ranking) |

---

## 8. Other tools you'll see cited

- **3D-ICE** (EPFL): thermal simulator with microchannel cooling for 3D ICs.
- **McPAT / CACTI**: power, area and timing models; they produce the power HotSpot needs.
- **Sniper / gem5**: performance simulators feeding McPAT.
- **ANSYS Icepak, Cadence Celsius**: commercial FEM/CFD tools, the reference HotSpot is
  validated against.

---

## 9. Compact reference list

1. K. Skadron et al., "Temperature-Aware Microarchitecture," ISCA 2003.
2. W. Huang et al., "HotSpot: A Compact Thermal Modeling Methodology for Early-Stage VLSI Design," IEEE TVLSI 14(5):501–513, 2006.
3. W. Huang et al., "An Improved Block-Based Thermal Model in HotSpot 4.0 with Granularity Considerations," WDDD 2007.
4. W. Huang et al., "Accurate, Pre-RTL Temperature-Aware Design Using a Parameterized, Geometric Thermal Model," IEEE Trans. Computers, 2008.
5. R. Zhang, M. R. Stan, K. Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," UVA TR CS-2015-04, 2015.
6. S. Pagani, J.-J. Chen, M. Shafique, J. Henkel, "MatEx: Efficient Transient and Peak Temperature Computation for Compact Thermal Models," DATE 2015, pp. 1515–1520.
7. S. Sharifi, C. Liu, T. S. Rosing, "Accurate Temperature Estimation for Efficient Thermal Management," ISQED 2008.
8. S. Sharifi, T. S. Rosing, "Accurate Direct and Indirect On-Chip Temperature Sensing for Efficient Dynamic Thermal Management," IEEE TCAD, 2010.
9. A. Ziabari, J.-H. Park, E. K. Ardestani, J. Renau, S.-M. Kang, A. Shakouri, "Power Blurring: Fast Static and Transient Thermal Analysis Method for Packaged Integrated Circuits and Power Devices," IEEE TVLSI 22(11):2366–2379, 2014.
10. A. K. Coskun, T. S. Rosing, K. C. Gross, "Utilizing Predictors for Efficient Thermal Management in Multiprocessor SoCs," IEEE TCAD 28(10), 2009.
11. I. Yeo, C. C. Liu, E. J. Kim, "Predictive Dynamic Thermal Management for Multicore Systems," DAC 2008, pp. 734–739.
12. K. Zhang, A. Guliani, S. Ogrenci-Memik, G. Memik, K. Yoshii, R. Sankaran, P. Beckman, "Machine Learning-Based Temperature Prediction for Runtime Thermal Management Across System Components," IEEE TPDS 29(2):405–419, 2018.
13. G. Singla, G. Kaur, A. K. Unver, U. Y. Ogras, "Predictive Dynamic Thermal and Power Management for Heterogeneous Mobile Platforms," DATE 2015.
14. S. Sadiqbatcha, J. Zhang, H. Amrouch, S. X.-D. Tan, "Real-Time Full-Chip Thermal Tracking: A Post-Silicon, Machine Learning Perspective" (RealMaps), IEEE Trans. Computers, 2021.
15. Q. Gu et al., "TherMapNet: Attention-Guided Runtime Full-Chip Thermal Map Prediction from Performance Metrics," arXiv 2608.21887, 2026.
16. V. A. Chhabria et al., "Thermal and IR Drop Analysis Using Convolutional Encoder-Decoder Networks," ASP-DAC 2021.
17. L. Chen, W. Jin, S. X.-D. Tan, "Fast Thermal Analysis for Chiplet Design based on Graph Convolution Networks," ASP-DAC 2022.
18. "Real-Time Temperature Prediction for Large-Scale Multi-Core Chips Based on Graph Convolutional Neural Networks," Electronics 14(6):1223, 2025.
19. Z. Liu et al., "DeepOHeat: Operator Learning-based Ultra-fast Thermal Simulation in 3D-IC Design," DAC 2023.
20. X. Liu, S. Liu, B. Yu, S. Chen, Q. Xu, "ThePlace: Thermal-Aware Placement With Operator Learning-Based Ultra-Fast Simulator," ASP-DAC 2025, pp. 900–906.
21. D. Huang, W. Yang, K. Ding, H. Xin, "IC-ThermBench: An Open, Progressive Benchmark for Generalizable 2.5D/3D-IC Thermal Learning," arXiv 2608.23977, 2026.
22. K. Sankaranarayanan, S. Velusamy, M. R. Stan, K. Skadron, "A Case for Thermal-Aware Floorplanning at the Microarchitectural Level," JILP 8, 2005.
23. Y. Ma et al., "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems," DATE 2021.
24. L. Siddhu, R. Kedia, S. Pandey, M. Rapp, A. Pathania, J. Henkel, P. R. Panda, "CoMeT: An Integrated Interval Thermal Simulation Toolchain for 2D, 2.5D, and 3D Processor-Memory Systems," ACM TACO, 2022.
25. L. Siddhu, R. Kedia, P. R. Panda, "FastCool: Leakage Aware Dynamic Thermal Management of 3D Memories," DATE 2019; journal version ACM TODAES 26(2), 2020.
26. L. Siddhu, R. Kedia, P. R. Panda, "CoreMemDTM: Integrated Processor Core and 3D Memory Dynamic Thermal Management for Improved Performance," DATE 2022.
27. L. Siddhu, A. Bagchi, R. Kedia, I. Ahmad, S. Pandey, P. R. Panda, "Dynamic Thermal Management of 3D Memory through Rotating Low Power States and Partial Channel Closure," ACM TECS, 2023.
28. A. Pathania, J. Henkel, "HotSniper: Sniper-Based Toolchain for Many-Core Thermal Simulations in Open Systems," IEEE ESL, 2018.

---

# Part B: References behind the models

Every source the project relies on, grouped by what it supports. For the full discussion of each
paper see Part A (§ numbers below point there) and `dataset.md`. Model names are from
`plan.md` and `src/ltp/models.py`:

| id | model | where |
|---|---|---|
| S0 | power blurring (no calibration) | `src/ltp/baselines.py`, P1-3, P2-1 |
| S1 | steady influence matrix, T = T_amb + G·P | P1-1, P2-1 |
| S1-hot-max | S1 on every grid cell inside each core; per core, the hottest | P2-3 |
| S2 | compressed G (shared package term + k neighbours) | P2-1 |
| T1 | first-order lag per core | P1-1, P3-1 |
| T2 | ARX (power-aware autoregressive) | P1-2, P3-1, P3-2 |
| T3 | sum of M exponentials with shared time constants | P1-1, P3-1 |
| T4 | exact state space + model-order reduction | P3-4 |

## How trustworthy is each entry

Each entry carries one of these tags.

- **[cited]**: the source is named in this repo's own docs (Part A, `dataset.md`, code
  docstrings). Part A states that for most papers only the abstract and author pages
  were read, and numbers taken from abstracts are marked *(abstract)* there. **Check the primary
  source before quoting any number or equation in the report.**
- **[background]**: a standard textbook or paper behind a technique we use, but not cited
  anywhere in the repo. I added these from general knowledge while compiling this file. They
  have not been opened or checked against the repo, so verify the details (title, year, venue,
  pages) before they go into a bibliography.
- **[source]**: software or documentation we actually ran.

---

## B1. HotSpot: the ground truth, and why it is linear

| Claim in the project | Reference | Tag |
|---|---|---|
| HotSpot is a compact RC network (heat = current, temperature = voltage); die, TIM, spreader, sink and air are nodes with lateral and vertical R and C | K. Skadron et al., "Temperature-Aware Microarchitecture," ISCA 2003 (Part A §2.1) | [cited] |
| The main HotSpot model description; the network is linear, so without leakage T = T_amb + R·P exactly for a fixed floorplan (P0-2 verifies this numerically to about 10⁻⁶ K) | W. Huang, S. Ghosh, S. Velusamy, K. Sankaranarayanan, K. Skadron, M. R. Stan, "HotSpot: A Compact Thermal Modeling Methodology for Early-Stage VLSI Design," IEEE TVLSI 14(5):501–513, 2006. [PDF](https://www.cs.virginia.edu/~skadron/Papers/hotspot_tvlsi06.pdf) (Part A §2.2) | [cited] |
| Block model loses accuracy on large or elongated blocks, which motivated the grid model (P0-3 chooses the grid) | W. Huang et al., "An Improved Block-Based Thermal Model in HotSpot 4.0 with Granularity Considerations," WDDD 2007. [PDF](https://www.cs.virginia.edu/~skadron/Papers/wddd07-UVA-hotspot-final.pdf) (§2.3) | [cited] |
| HotSpot validated against finite-element tools (roughly 1–2 °C); bounds how far "predicts HotSpot" can be read as "predicts silicon" | W. Huang et al., "Accurate, Pre-RTL Temperature-Aware Design Using a Parameterized, Geometric Thermal Model," IEEE Trans. Computers, 2008. [preprint](https://www.cs.virginia.edu/~skadron/Papers/hotspot_tc08_preprint.pdf) (§2.3) | [cited] |
| The version we run: IBM calibration, SuperLU direct solver, heterogeneous 3D layers, layer files (`.lcf`) | R. Zhang, M. R. Stan, K. Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," UVA Tech. Report CS-2015-04, 2015. [PDF](https://www.cs.virginia.edu/~skadron/Papers/HotSpot60_TR.pdf) (§2.4) | [cited] |
| The tool itself, its README and example configs (example1 package: ambient 45 °C, spreader 30 mm, sink 60 mm) | HotSpot source, https://github.com/uvahotspot/HotSpot (submodule in `HotSpot/`, see `.gitmodules`); `HotSpot/README.md`, `HotSpot/examples/example1/` | [source] |
| HotSpot's transient step is one backward-Euler step per sampling interval, (C/h + G)·T⁺ = (C/h)·T + P; this is why its transient is an exactly linear discrete-time system for a fixed step (used in P0-4 and P3-4) | `HotSpot/RCutil.c` and `HotSpot/temperature_grid.c` (backward Euler, SuperLU path) | [source] |
| HotSpot is the standard label generator in this field (so "HotSpot-trained" is a legitimate design if the report says it predicts HotSpot) | Chen, Jin, Tan (ASP-DAC 2022), the 2025 multi-core GCN paper and IC-ThermBench, all in §5 below (Part A §2.4) | [cited] |

## B2. Steady-state models (S0, S1, S1-hot-max, S2)

| Model / claim | Reference | Tag |
|---|---|---|
| **S1**: superposition. Run N times with 1 W in one block; matrix G is then exact and each prediction is one matrix–vector product | No single paper. Standard linear-systems superposition, noted in Part A §3.1; justified for HotSpot by the linearity in Huang et al. 2006 and verified in P0-2 | [cited] |
| **S0**: power blurring. Convolve the power map with a point-source response kernel (we measure one radial kernel on a 28 mm reference die) | A. Ziabari, J.-H. Park, E. K. Ardestani, J. Renau, S.-M. Kang, A. Shakouri, "Power Blurring: Fast Static and Transient Thermal Analysis Method for Packaged Integrated Circuits and Power Devices," IEEE TVLSI 22(11):2366–2379, 2014. [PDF](https://users.soe.ucsc.edu/~renau/docs/tvlsi13.pdf) (Part A §3.4) | [cited] |
| **S1-hot-max**: block averages hide hot spots, so output the hottest grid cell per core | Motivated by the block-versus-grid limits in Huang et al. (WDDD 2007, TC 2008) above; the all-cells matrix and its compression are our own design (P2-3) | [cited] |
| **S2**: compressed G with a shared package term | Our own design (plan.md §3); no source | none |
| Learned alternatives compared against S1 in P1-3 (calibration-free regression) and the accuracy targets | IC-ThermBench (§5 below) | [cited] |

## B3. Transient models (T1, T2, T3, T4)

| Model / claim | Reference | Tag |
|---|---|---|
| **T3**: the step response of a linear RC network is a sum of exponentials (its modal expansion), so G_ij(t) = Σ_m a_ijm (1 − e^(−t/τ_m)) with shared τ_m | Follows from the first-order ODE form C·dT/dt = −G·T + P used by HotSpot and by MatEx. The fitting procedure (nonlinear least squares, `scipy.optimize.least_squares`) is ours | [cited] for MatEx; the equation is ours |
| Matrix-exponential solution of compact thermal models | S. Pagani, J.-J. Chen, M. Shafique, J. Henkel, "MatEx: Efficient Transient and Peak Temperature Computation for Compact Thermal Models," DATE 2015, pp. 1515–1520. [PDF](https://cesdownloads.itec.kit.edu/pdf/pagani/Pagani-DATE-2015-MatEx.pdf) (Part A §3.2) | [cited] |
| **T1**: first-order lag per core, one time constant | Simplest case of the same ODE; no specific source. The experiment shows it is 13–14 K wrong somewhere (P1-1) | none |
| **T2**: ARX with the steady gain fixed to G | A. K. Coskun, T. S. Rosing, K. C. Gross, "Utilizing Predictors for Efficient Thermal Management in Multiprocessor SoCs," IEEE TCAD 28(10), 2009 (ARMA on temperature; Part A §4.1). Power-aware identified models on real devices: G. Singla, G. Kaur, A. K. Unver, U. Y. Ogras, "Predictive Dynamic Thermal and Power Management for Heterogeneous Mobile Platforms," DATE 2015; Bhat, Gumussoy, Ogras, TVLSI 2017/2018, [arXiv 2003.11081](https://arxiv.org/pdf/2003.11081) (§4.4) | [cited] |
| ARX / least-squares system identification in general (model structure, order selection, stability) | L. Ljung, *System Identification: Theory for the User*, 2nd ed., Prentice Hall, 1999 | [background] |
| **T4**: exact state space C·x′ = −G·x + B·p, y = W·x, built from HotSpot's own matrices | Same ODE form as MatEx (above). Reduced-order thermal models inside Kalman estimators: S. Sharifi, C. Liu, T. S. Rosing, "Accurate Temperature Estimation for Efficient Thermal Management," ISQED 2008; S. Sharifi, T. S. Rosing, "Accurate Direct and Indirect On-Chip Temperature Sensing for Efficient Dynamic Thermal Management," IEEE TCAD, 2010. [ISQED PDF](https://cseweb.ucsd.edu//~shsharif/papers/sharifi_isqed08.pdf) (Part A §3.3) | [cited] |
| T4 reduction: modal truncation, then balanced truncation (square-root method) | B. C. Moore, "Principal Component Analysis in Linear Systems: Controllability, Observability, and Model Reduction," IEEE Trans. Automatic Control 26(1), 1981. A. C. Antoulas, *Approximation of Large-Scale Dynamical Systems*, SIAM, 2005. | [background] |
| Sparse direct solve (SuperLU) used by HotSpot and in our eigen-solves | J. W. Demmel, S. C. Eisenstat, J. R. Gilbert, X. S. Li, J. W. H. Liu, "A Supernodal Approach to Sparse Partial Pivoting," SIAM J. Matrix Anal. Appl. 20(3), 1999 | [background] |
| Run-time use of a fast transient predictor and its time scales (1 ms sampling, thermal lag after throttling) | L. Siddhu, R. Kedia, S. Pandey, M. Rapp, A. Pathania, J. Henkel, P. R. Panda, "CoMeT: An Integrated Interval Thermal Simulation Toolchain for 2D, 2.5D, and 3D Processor-Memory Systems," ACM TACO, 2022. [arXiv 2109.12405](https://arxiv.org/abs/2109.12405), [code](https://github.com/marg-tools/CoMeT) (Part A §6.2) | [cited] |

## B4. Leakage (temperature-dependent power; P4-3)

| Claim | Reference | Tag |
|---|---|---|
| HotSpot's built-in leakage model, used as the model our S1 + leakage loop assumes known: P_leak = α · area · e^(β (T − 383.15 K)), α = 1.5×10⁴ W/m², β = 0.036 K⁻¹, iterated with temperature to a fixed point; steady state only (HotSpot ignores it in transient runs) | HotSpot source: `-leakage_used` / `-leakage_mode` options in `HotSpot/temperature.c` (leakage iteration at about line 658; the transient warning at line 278), and our `experiments/P4-3_leakage/` | [source] |
| Leakage–temperature feedback and thermal runaway in 3D memories; leakage-aware DTM | L. Siddhu, R. Kedia, P. R. Panda, "FastCool: Leakage Aware Dynamic Thermal Management of 3D Memories," DATE 2019; journal version ACM TODAES 26(2), 2020. [PDF](https://www.cse.iitd.ac.in/~siddhulokesh/papers/FastCool_DATE2019.pdf) (Part A §6.2) | [cited] |
| Origin of the exponential leakage-versus-temperature form HotSpot implements | **Not identified.** HotSpot's source does not name a paper for it, and none is cited in this repo. Before the report states the equation's provenance, find the HotSpot documentation or the original leakage-modelling paper it builds on. I have not looked this up | open |

## B5. Learned surrogates and benchmarks (comparison and context)

| Work | Used for | Tag |
|---|---|---|
| D. Hang, W. Yang, K. Ding, H. Xin, J. Wei, "IC-ThermBench: An Open, Progressive Benchmark for Generalizable 2.5D/3D-IC Thermal Learning," arXiv 2608.23977, 2026 (preprint). [HTML](https://arxiv.org/html/2608.23977), [code](https://github.com/Day333/ThermalBench), data DOI 10.5281/zenodo.21992816. (`Part A` lists the authors as Huang, Yang, Ding, Xin; `dataset.md` gives the fuller author list above, so check the PDF.) Companion foundation model: Therm-FM, arXiv 2605.22663 | Accuracy targets (about 0.5–1 K within family), the package-change scenario in P4-2, and the finding that unseen-package accuracy is the open problem. Numbers differ between versions, so quote one version | [cited] |
| V. A. Chhabria et al., "Thermal and IR Drop Analysis Using Convolutional Encoder-Decoder Networks" (ThermEDGe), ASP-DAC 2021. [arXiv 2009.09009](https://arxiv.org/abs/2009.09009) | CNN surrogate baseline (D3) | [cited] |
| L. Chen, W. Jin, S. X.-D. Tan, "Fast Thermal Analysis for Chiplet Design based on Graph Convolution Networks," ASP-DAC 2022 | GCN trained on HotSpot; shows only 2.6× over HotSpot + SuperLU | [cited] |
| "Real-Time Temperature Prediction for Large-Scale Multi-Core Chips Based on Graph Convolutional Neural Networks," *Electronics* 14(6):1223, 2025. [DOI](https://doi.org/10.3390/electronics14061223) | Memory and complexity comparison against HotSpot and MatEx | [cited] |
| Z. Liu et al., "DeepOHeat: Operator Learning-based Ultra-fast Thermal Simulation in 3D-IC Design," DAC 2023. [code](https://github.com/Cadence-Celsius/DeepOHeat) | Operator-learning baseline | [cited] |
| X. Liu, S. Liu, B. Yu, S. Chen, Q. Xu, "ThePlace: Thermal-Aware Placement With Operator Learning-Based Ultra-Fast Simulator," ASP-DAC 2025, pp. 900–906. [PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C246-ASPDAC2025-ThePlace.pdf) | Predictor inside a placer (framing for the design-time demo) | [cited] |
| S. Sadiqbatcha, J. Zhang, H. Amrouch, S. X.-D. Tan, "Real-Time Full-Chip Thermal Tracking: A Post-Silicon, Machine Learning Perspective" (RealMaps), IEEE Trans. Computers, 2021; Q. Gu et al., "TherMapNet," arXiv 2608.21887, 2026 | Context: sensor/counter-based full-chip maps | [cited] |

## B6. Run-time management, mapping and floorplanning (use cases and demos)

| Work | Used for | Tag |
|---|---|---|
| A. K. Coskun et al., IEEE TCAD 2009 (above) | Proactive vs reactive management result (about 60 % fewer hot spots, *(abstract)*); framing for the TA's "reactive vs proactive scaling" request | [cited] |
| I. Yeo, C. C. Liu, E. J. Kim, "Predictive Dynamic Thermal Management for Multicore Systems," DAC 2008, pp. 734–739 | Closest ancestor of the core-selection demo (P6-3) | [cited] |
| K. Zhang, A. Guliani, S. Ogrenci-Memik, G. Memik, K. Yoshii, R. Sankaran, P. Beckman, "Machine Learning-Based Temperature Prediction for Runtime Thermal Management Across System Components," IEEE TPDS 29(2):405–419, 2018 | What "lightweight" means at run time; real-hardware error levels | [cited] |
| K. Sankaranarayanan, S. Velusamy, M. R. Stan, K. Skadron, "A Case for Thermal-Aware Floorplanning at the Microarchitectural Level," JILP 8, 2005 (HotFloorplan). [PDF](https://www.jilp.org/vol7/v7paper15.pdf) | Design-time use of a predictor | [cited] |
| Y. Ma et al., "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems," DATE 2021. [code](https://github.com/bu-icsg/TAP-2.5D) | Chiplet floorplan family; also the "TAP 2.5D" note about generating floorplans | [cited] |
| Q. Wang, X. Li, T. Jia, Y. Lin, R. Wang, R. Huang, "ATPlace2.5D: Analytical Thermal-Aware Chiplet Placement Framework for Large-Scale 2.5D-IC," ICCAD 2024. [DOI](https://dl.acm.org/doi/10.1145/3676536.3676648), [code](https://github.com/Brilight/ATPlace_pub). `dataset.md` §3 notes the paper itself was **not** opened, only the repo | Reference solver setup (HotSpot grid, `-detailed_3D on`) | [cited] |
| L. Siddhu, R. Kedia, P. R. Panda, "CoreMemDTM," DATE 2022; Siddhu et al., "Dynamic Thermal Management of 3D Memory through Rotating Low Power States and Partial Channel Closure," ACM TECS, 2023 | DTM policies that would consume a predictor | [cited] |
| A. Pathania, J. Henkel, "HotSniper: Sniper-Based Toolchain for Many-Core Thermal Simulations in Open Systems," IEEE ESL, 2018 | The toolchain CoMeT extends | [cited] |

## B7. Data and inputs

| Item | Source | Tag |
|---|---|---|
| 23 TA 2D floorplans (Style_1 to Style_4), 3D floorplans, `.flp` / `.lcf` / `.ptrace` formats, power ranges (big 10–20 W, little 5–10 W), nominal values (big 20 W, little 8 W), and the correction to the Style_2 power traces | TA sample dataset, `data/sample_dataset/README.md` and files; the TA's confirmation that Style_2 fp_001/002/003/005 had the big- and little-core power swapped (corrected in this repo; see `experiments/P0-5_ta_floorplans/README.md`) | [source] |
| EV6 floorplan and `gcc.ptrace` (P3-1 EV6 check) | HotSpot examples, `HotSpot/examples/example1/`; the EV6 floorplan originates from Skadron et al., ISCA 2003 | [source] |
| Generated floorplans and power traces | Our own generators: `src/sim/tagen.py`, `src/sim/flpgen.py`, `src/sim/powergen.py`. They imitate the TA styles and ranges and are not the TA's generator | ours |

## B8. Software

| Tool | Used for | Tag |
|---|---|---|
| HotSpot 6.0 (patched build: 6-decimal output and cached LU factorisation, `setup/build_hotspot_ltp.sh`) | Ground truth for every experiment | [source] |
| SuperLU (via HotSpot `make SUPERLU=1`) | Grid-model steady state and transient | [source] |
| NumPy, SciPy (`scipy.optimize.least_squares` for T3, `scipy.sparse.linalg` for T4, `scipy.linalg` for balanced truncation), Matplotlib, WSL2 Ubuntu | Models, fits and plots | [source] |
| CoMeT, McPAT/CACTI, Sniper/gem5, 3D-ICE, ANSYS Icepak, Cadence Celsius | Mentioned in Part A §8 as related tools; none was run | [cited] |

---

## B9. Calibration time of each model

Time to prepare each model for one floorplan, from our own runs (P0-4, P1-1, P1-2, P1-3, P2-3,
P3-4, P4-2, P4-3). The clock is dominated by HotSpot runs, so the table counts those first.
Reference costs on our machine (WSL2, 20 logical CPUs, 7 GB RAM, grid 64×64): one steady
HotSpot run takes **0.24 s**, and a transient step takes **5.2–5.9 ms** (P0-4). Running 8 at
once is the fastest setting but slows each run down, which is why some figures below are in
CPU-seconds.

| model | what calibration needs | time per floorplan | source |
|---|---|---|---|
| **S0** power blurring | No runs on the target floorplan. One shared kernel from a single point-source run on a 28 mm reference die (128×128 grid), measured once and cached | 0 for each new floorplan. The one-off kernel run was **not timed** | P1-3 |
| **S1** influence matrix | 8 steady HotSpot runs (1 W in one core each) | **4.3 s** | P1-1 |
| **S1-hot-max** (hot cells) | Nothing extra: the same 8 runs also write the 64×64 maps | same 4.3 s | P2-3 |
| **S2** compressed G | Nothing extra: built from S1's G | negligible (fit time **not timed**) | P2-1 |
| **T1** first-order lag | The step-response runs shared with T3 (the 24-run set below) | about **5 min** | P1-1 |
| **T3** sum of exponentials (M = 4) | 24 HotSpot runs (3 per core, covering 1 ms to 100 s), shared with S1 and T1. The least-squares fit is small next to the runs | about **5 min on an idle core** (1,310 CPU-s with 8 runs in parallel) | P1-1 |
| **T2** ARX (2,2) | S1's G, plus one 60 s excitation trace of 60,000 steps (5.5 min on an idle core, 1,250 s with four in parallel). The 20 s prefix that works best costs about a third | about **1.8 min** (20 s trace) to **5.5 min** (60 s trace), plus S1's 4.3 s. The fit itself was **not timed** | P1-2 |
| **T4** exact state space, reduced | Needs a separate debug HotSpot build that exports the matrices (built once), then modal and balanced truncation of the 16,396-state system | **11–15 s** reduction per floorplan, plus the one-off build and export | P3-4 |
| **S1 + leakage loop** | S1's runs plus one steady run per FILL block, 11–25 steady runs in total instead of 8 | about **3–17 extra runs, 1–4 s** (at 0.24 s each) | P4-3 |
| **Recalibration after a package change** | The same 24 runs under the new package. A change of ambient temperature needs none | about **5 CPU-min** per floorplan idle (1,200–3,000 CPU-s in parallel) | P4-2 |

**Whole-dataset figures.** The 24 TA floorplans took 576 runs and **66 min** of wall time for
S1, T1 and T3 together (P1-1). The first full run of P1-1 is "about 70 min", and later fits from
the cached runs take minutes.

**What "calibration time" leaves out.**
- *Fit time* (the least-squares and matrix work after the HotSpot runs) was not recorded
  separately for S1, S2, T1, T3 or T2. I'd expect it to be small compared with the runs, but that
  is an expectation, not a measurement.
- *Per-prediction time* is a different cost, in microseconds, and is reported in P2-1 and P3-1.
- *Test cost*: the ground-truth HotSpot runs that score the models (for example 7,248 steady runs
  in P2-1) are not part of calibration.
- For scale, S1 alone is 8 runs, and T3 (24 runs) is about 70× the HotSpot time of S1 alone, so
  S1 is the cheap model and T3 and T2 are where the calibration time goes.


