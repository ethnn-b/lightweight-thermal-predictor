# Demo: a new floorplan and new power, HotSpot vs S1 / T3

## Step by step (one command per step)

Inside WSL. Pick the style and seed first; `N` is the floorplan's name, `demo_s<style>_<seed>`.

```bash
cd "/mnt/c/IITH Downloads/acads/comp architecture/Project/lightweight-thermal-predictor"
export PYTHONPATH=$PWD OPENBLAS_NUM_THREADS=1
HS=~/projects/HotSpot-ltp/hotspot
N=demo_s2_2026; D=demo/output/$N

# 1. new floorplan
python3 demo/new_floorplan.py --style 2 --seed 2026
cat $D/${N}_layer_0.flp

# 2. new power (steady vector + 2 s transient trace)
python3 demo/new_power.py $D

# 3. HotSpot: steady (with 64x64 map), then transient (64x64 map every step)
cp configs/base_grid64.config $D/hotspot.config
cd $D
time $HS -c hotspot.config -f ${N}_layer_0.flp -p steady_power.ptrace -model_type grid \
     -grid_layer_file $N.lcf -grid_rows 64 -grid_cols 64 \
     -steady_file hotspot.steady -grid_steady_file hotspot.grid.steady
time $HS -c hotspot.config -f ${N}_layer_0.flp -p transient_power.ptrace -model_type grid \
     -grid_layer_file $N.lcf -grid_rows 64 -grid_cols 64 -sampling_intvl 0.001 \
     -o hotspot.ttrace -grid_transient_file /tmp/hotspot.grid.ttrace | tail -n 2
cd -

# 4. calibrate the predictor on the new floorplan (24 HotSpot runs, ~2 min, once per floorplan)
python3 -m src.ltp calibrate $D -o $D/model.npz

# 5. predict: S1 (steady) and T3 (transient)
python3 -m src.ltp steady $D/model.npz --ptrace $D/steady_power.ptrace -o $D/s1.steady | cut -f1-8
python3 -m src.ltp transient $D/model.npz --ptrace $D/transient_power.ptrace --dt 0.001 -o $D/t3.ttrace

# 6. compare and draw the maps
python3 demo/compare.py $D
rm /tmp/hotspot.grid.ttrace          # ~0.5 GB, only needed by step 6
```

Files in `demo/output/<name>/` (git-ignored): the floorplan (`.flp`, `_tim.flp`, `.lcf`), the power
(`.ptrace`), HotSpot's outputs (`hotspot.*`), the model (`model.npz`), the predictions
(`s1.steady`, `t3.ttrace`) and:

| file | contents |
|---|---|
| `1_floorplan.png`, `2_power_trace.png` | the new floorplan and transient power |
| `3_steady_maps.png` | HotSpot 64 x 64 map, HotSpot block averages, S1, difference (µK) |
| `4_transient_maps_end.png` | at the end of the trace: HotSpot 64 x 64 map, HotSpot block averages, T3, difference (K) |
| `5_transient_over_time.png` | every core over time, HotSpot vs T3, and the worst error |
| `summary.txt`, `cores.csv` | per-core temperatures, errors, prediction times, model size |

S1 and T3 predict one temperature per block, so their maps are painted per block and compared
with HotSpot's block averages; HotSpot's 64 x 64 map is shown next to them for the hot spots
inside the cores.

## All in one

`bash demo/run_demo.sh [--style 1-4] [--seed N] [--steps N]` does the same in one go and writes
`demo/output/<name>/` with the floorplan in a `floorplan/` subfolder.
