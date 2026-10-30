# Experiments

Beginner-friendly overview of everything below: [`docs/guide.html`](../docs/guide.html) (open in a browser).

One folder per experiment (`<ID>_<name>/`): `run.py` (the experiment), `README.md` (question,
setup, results, conclusion) and `results/` (CSVs, figures, `log.txt`). IDs follow `plan.md` §5.

**Run** (inside WSL, from the repo root): `bash experiments/run.sh <ID>_<name>`.
One-time setup: `bash setup/build_hotspot_ltp.sh` (patched HotSpot, see P0-4). HotSpot runs are
cached in `~/ltp_runs/`, so reruns only redo the analysis. Run order matters only through those
caches: P1-1 first, then P1-2, then the rest.

Reference: HotSpot grid model 64×64 with the TA layer stack, ambient 45 °C, Δt = 1 ms.
Floorplans: the 23 TA 2D floorplans (+ HET-A, EV6, generated ones where stated).

| ID | experiment | headline result |
|---|---|---|
| P0-1 | example1 reproduced | done earlier (`README_SETUP.md`) |
| [P0-2](P0-2_linearity/) | linearity | HotSpot is linear to 10⁻⁶ K, steady and transient |
| [P0-3](P0-3_block_vs_grid/) | block vs grid model | block model is 1–5 K off; 64×64 is converged; hottest cell 3–4 K above core average |
| [P0-4](P0-4_infrastructure/) | infrastructure, HotSpot timing | patched HotSpot: 6-decimal output, 29× faster transients (identical results); 0.24 s per steady run, ~5.5 ms per step |
| [P0-5](P0-5_ta_floorplans/) | TA floorplans | all 23 run at 69–77 °C; a little core is always hottest; Style_2 TA ptraces put big power on little cores (~100 °C) |
| [P0-5d](P0-5d_generated_floorplans/) | generated floorplans | 40 more floorplans in the TA styles, same temperature range |
| [P1-1](P1-1_step_calibration/) | calibration by step runs | 24 HotSpot runs per floorplan; S1 exact from 8; T3 fit 0.46 K (M = 4) / 0.12 K (M = 6) |
| [P1-2](P1-2_trace_calibration/) | calibration from one trace (ARX) | needs ≥ 5 s; best 0.21 K mean, 1 K worst; T3 is 3–5× better |
| [P1-3](P1-3_is_calibration_needed/) | is calibration needed? | yes: without it 0.5–2.7 K mean, 3–12 K worst, wrong hottest core 20–60 %; S1 3×10⁻⁵ K |
| [P2-1](P2-1_steady_predictor/) | steady predictor | S1: 3×10⁻⁵ K worst, 2.6 µs, 464–928 B, ~90,000× faster than HotSpot; S2 shrinks 64 cores 5.8× at 0.6 K |
| [P2-2](P2-2_layout_effects/) | layout effects | edges, distance and die size explain why G differs; white space keeps chips cooler (r = −0.83) |
| [P2-3](P2-3_hot_spots/) | hot spots inside cores | core average misses the peak by up to 9 K; S1-hot-max (3 kB) predicts it within 0.08 K mean |
| [P3-1](P3-1_transient_predictor/) | transient predictor | T3 M = 4: 0.06–0.09 K mean, 0.3 K worst, 3 µs/step (~1,800× HotSpot); also on EV6 + real gcc trace |
| [P3-2](P3-2_forecast_horizon/) | forecast vs horizon | T3 anchored on sensors: < 0.005 K mean 10 ms ahead; persistence up to 8 K |
| [P3-3](P3-3_pareto/) | accuracy / size / time | T3 is the Pareto front from 2 to 6 kB; T4 only below 0.05 K |
| [P3-4](P3-4_state_space_T4/) | exact state space + reduction (T4) | HotSpot's own matrices reproduce it to 10⁻⁶ K; 32 states → 0.047 K |
| [P4-1](P4-1_robustness/) | robustness | unaffected by power level, burstiness, migration; weak spot: other Δt (calibrate at the DTM Δt) |
| [P4-2](P4-2_recalibration/) | recalibration after a package change | ambient change: no recalibration (only T_amb); heat-sink change: 4–8.5 K off until recalibrated (24 runs) |
| [P4-3](P4-3_leakage/) | leakage | ignoring it costs 0.1 K (1 K at 10× leakage); a fixed-point loop removes it |
| [P5-1](P5-1_ltp_package/) | `ltp` package | `python3 -m src.ltp calibrate / steady / transient / forecast / bench`; 7 unit tests |
| [P6-1](P6-1_closed_loop_hotspot/) | closed-loop HotSpot | HotSpot driven step by step through pipes; identical to a normal run |
| [P6-2](P6-2_dtm/) | reactive vs proactive DTM | proactive DTM with T3 forecasts: 60–130× less time over the limit than reactive, for 1–1.6 % throughput; without a model it is 20–30× worse |
| [P6-3](P6-3_core_selection_demo/) | which cores to switch on | S1 picks the same coolest placement as HotSpot on all 4 floorplans, ~8,000,000× faster |
