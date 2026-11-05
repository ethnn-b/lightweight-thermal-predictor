# Generated transient power traces

Copied from the WSL cache `~/ltp_runs` on 2026-11-01. These are our own power traces (the TA's
`*_transient.ptrace` files are constant), with the HotSpot temperatures they produce
(grid 64×64, ambient 45 °C, step 1 ms, cold start). Every file can be regenerated from its seed
by `src/sim/datasets.py` and `src/sim/powergen.py`.

Name pattern: `trace_<floorplan>_<kind>_<steps>_<tag>_dt0.001`

| kind / tag | what it is | used for |
|---|---|---|
| `excitation_60000_cal` | 60 s, random levels over the full range per core | calibration (T2 ARX) |
| `phase_10000_test0/1` | 10 s, 4 DVFS-like levels, phases 1 ms–2 s | testing |
| `phase_2000_short` | 2 s phase trace | testing on all floorplans |
| `phase_2000_bench` | 2 s phase trace | timing benchmark |
| `custom_gcc` (ev6) | HotSpot's example `gcc.ptrace` | EV6 check |

Folders:

- `npz/`: the cache files as written. Arrays: `P` (steps × cores, W), `T` (steps × blocks, K),
  `wall_s` (HotSpot run time, s).
- `ptrace/`: the same data as text. `<name>.ptrace` is the HotSpot input in TA format (all
  blocks, FILL = 0 W); `<name>.temps_C.tsv` is the HotSpot output per block in °C, one row per step.
- `runs/<experiment>/<run>/`: HotSpot inputs (`power.ptrace`), outputs (`out.ttrace`, if kept)
  and `meta.json` from the P0-4, P4-1, P6-1, P6-2 and scratch run folders.
