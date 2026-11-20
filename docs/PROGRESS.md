# Progress log

Short dated notes: who did what, and what was found. Details are in each
`experiments/<ID>_<name>/README.md`.

- 2026-10-29 K: `flpgen.py` with HET-A and HOM-16; TA sample dataset added under
  `data/sample_dataset/` (branch `p0-flpgen`).
- 2026-10-30 E: plan revised for the TA dataset (`plan.md`, `dataset.md`).
- 2026-10-30 E: patched HotSpot build (`setup/`): 6-decimal output, LU factorisation reused in
  grid transients (bit-identical, 29× faster). Python infrastructure in `src/sim/`.
- 2026-10-30 E: P0-2 HotSpot is linear to 10⁻⁶ K (steady and transient).
- 2026-10-30 E: P0-3 block model is 1–5 K off the grid model; 64×64 converged (≤ 0.15 K);
  hottest cell is 3.3–4 K above core average.
- 2026-10-30 E: P0-4 HotSpot reference: 0.24 s per steady run, ~5.5 ms per 1 ms transient step;
  8 parallel workers is the sweet spot.
- 2026-10-30 E: P0-5 all 23 TA floorplans run: 69–77 °C at nominal power, a little core is always
  hottest; Style_2 TA ptraces give ~100 °C (big power on little cores); s3_fp004 = s3_fp005
  rotated.
- 2026-10-30 E: P0-5d 40 more floorplans in the TA styles generated (`src/sim/tagen.py`).
- 2026-10-30 E: P1-1 all 24 floorplans calibrated (24 HotSpot runs each, 66 min total). S1 needs
  8 runs (4 s); T3 fit error 0.46 K at M = 4, 0.12 K at M = 6 (worst floorplan); T1 is 14 K off
  (time constants span 1 ms to 8 s). Little cores self-heat 2.4x big cores; edge cores more.
- 2026-10-30 E: found and fixed a memory leak in HotSpot's grid transient (power vector never
  freed; a 60 s trace needed ~8 GB and was killed). Output unchanged, memory flat at 115 MB.
- 2026-10-30 E: P1-2 ARX from one trace: needs ≥ 5 s; best 0.21 K mean / 1.0 K worst; (3,3) on
  all blocks unstable. T3 from step runs is 3-5x better.
- 2026-10-30 E: P1-3 calibration is needed: every calibration-free method is 0.5-2.7 K off on
  average, 3-12 K worst; S1 is 3e-5 K. Best uncalibrated: S0 + learned correction (0.55 K).
- 2026-10-30 E: P2-1 S1: 3e-5 K worst, 2.6 us, 464-928 B, ~90,000x faster than HotSpot.
  S2 (neighbours + per-row package term) shrinks HOM-64 from 33 kB to 5.7 kB at 0.6 K.
- 2026-10-30 E: P2-2 layout effects: edges (+8-27 % self-heating), distance, die size; peak vs
  core coverage r = +0.83. P2-3 hot spots: core average misses the peak by up to 9 K; the hot
  spot moves. (Updated 2026-11-07: S1-hot-max now uses every cell inside each core, exact at
  115 kB; dropping cells that can never be the hottest over the TA power range plus float16 gives
  3.3 kB at 0.002 K mean, 0.011 K worst. The earlier candidate-cell version was removed.)
- 2026-10-30 E: P3-1 T3 M=4: 0.06-0.09 K mean, 0.3 K worst, 3 us/step (~1,800x HotSpot); works on
  EV6 + real gcc trace. P3-2 T3 anchored on sensors: < 0.005 K at 10 ms ahead; persistence 8 K.
  P3-3 Pareto: T3 is the front 2-6 kB. P3-4 T4 from HotSpot's own matrices: exact (1e-6 K); 32
  states -> 0.047 K, needs a fast-mode filter.
- 2026-10-30 E: P4-3 leakage: 0.1 K (default) / 1 K (10x) error, removed by a fixed-point loop.
  P5-1 `python3 -m src.ltp` CLI + 7 unit tests. P6-1 closed-loop HotSpot stepper, exact.
  P6-3 S1 picks the same coolest core placement as HotSpot on all 4 floorplans, ~8e6x faster.
- 2026-10-30 E: P4-1 robustness: unaffected by power level (3x), burstiness, migration; other Δt
  costs ~1 K worst (calibrate at the DTM Δt). P4-2 ambient change needs no recalibration; heat
  sink change 4-8.5 K off until recalibrated. P6-2 proactive DTM (T3 forecast) cuts time over the
  limit 60-130x vs reactive for 1-1.6 % throughput; persistence (no model) 20-30x worse than T3.
  All experiments done; index in experiments/README.md.
