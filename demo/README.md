# Demo: a new floorplan and new power, HotSpot vs S1 / T3

```bash
# inside WSL
cd "/mnt/c/IITH Downloads/acads/comp architecture/Project/lightweight-thermal-predictor"
bash demo/run_demo.sh                       # random style and seed: a floorplan never seen before
bash demo/run_demo.sh --style 3 --seed 4242 # reproducible; reruns with a used seed skip calibration
```

Options: `--style 1-4` (TA style, default random), `--seed N` (default: new), `--steps N`
(transient length in 1 ms steps, default 2000 = 2 s).

What it does:

1. Generates a new floorplan with the TA-style rules of `src/sim/tagen.py` (2 big + 6 little cores,
   white space tiled with FILL blocks), written to `output/<name>/floorplan/`.
2. Generates a new random steady power vector and a new phase trace (cores switch between 4 power
   levels independently), both saved as `.ptrace`.
3. Runs HotSpot (64 x 64 grid): steady map, and the transient map at the last step (cold start).
4. Calibrates the predictor on the new floorplan (24 HotSpot runs, about 2 min with 8 workers;
   cached in `~/ltp_runs/calib/`), then predicts with S1 (steady) and T3, M = 4 (transient).
5. Writes to `output/<name>/`:

| file | contents |
|---|---|
| `1_floorplan_and_power.png` | the new floorplan and the transient power trace |
| `2_steady_maps.png` | HotSpot 64 x 64 map, HotSpot block averages, S1, difference (µK) |
| `3_transient_maps_end.png` | at the end of the trace: HotSpot 64 x 64 map, HotSpot block averages, T3, difference (K) |
| `4_transient_over_time.png` | every core over time, HotSpot vs T3, and the worst error |
| `summary.txt`, `cores.csv` | timings, errors, per-core temperatures |
| `model.npz`, `maps.npz`, `*.ptrace`, `floorplan/` | the model file, raw maps, inputs |

S1 and T3 predict one temperature per block, so their maps are painted per block and compared
with HotSpot's block averages; HotSpot's 64 x 64 map is shown next to them for the hot spots
inside the cores.
