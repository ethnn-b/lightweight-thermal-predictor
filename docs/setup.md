# HotSpot setup and example1 run

What was done so far, how to repeat it, and where everything is.

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Home |
| Linux layer | WSL2, Ubuntu (a regular user account) |
| Packages installed in Ubuntu | `build-essential` (gcc 15.2, make 4.4), `python3`, `python3-pip`, `rsync`, `python3-pandas`, `python3-matplotlib` |

WSL was installed from an administrator PowerShell with `wsl --install -d Ubuntu`.

## 2. Where things live

| What | Location |
|---|---|
| HotSpot source and built binary (Linux side, used for runs) | `~/projects/HotSpot` inside Ubuntu |
| Same files seen from Windows | `\\wsl$\Ubuntu\home\<user>\projects\HotSpot` |
| Original HotSpot download (untouched) | `HotSpot/` in this folder |
| Analysis scripts | `setup/example1/` (and a copy in `~/projects/HotSpot/analysis`) |
| Copy of example1 inputs and outputs | `setup/example1/results/` |

Runs happen in the Linux copy because file I/O there is much faster than under `/mnt/c`.
The Windows `HotSpot/` folder is just the pristine source.

## 3. Build

```bash
cd ~/projects/HotSpot
make SUPERLU=1  # produces ./hotspot, ./hotfloorplan, libhotspot.a
```

HotSpot is built with the SuperLU solver (packages `libsuperlu-dev`, `libblas-dev`). It speeds up
grid-model steady state, allows grid sizes that aren't powers of two, and is required for the
microfluidic example (example5). A plain `make` also works but loses those features.

## 4. Run example1

```bash
cd ~/projects/HotSpot/examples/example1
bash run.sh
```

`run.sh` runs HotSpot twice:

1. Block model on the `ev6.flp` floorplan with the `gcc.ptrace` power trace. This writes the
   steady-state temperatures to `outputs/gcc.steady`.
2. Copies those steady temperatures to `gcc.init` and re-runs the transient simulation from
   them, so the chip starts warm. This writes `outputs/gcc.ttrace`.

Note: files copied from Windows can have CRLF line endings that break bash scripts.
Fix with `sed -i 's/\r$//' run.sh`.

### Inputs (in `examples/example1/`)

| File | Meaning |
|---|---|
| `ev6.flp` | Floorplan: block names, sizes, positions |
| `gcc.ptrace` | Power trace in watts: one column per block, 100 rows |
| `example.config` | Model parameters. Ambient is 318.15 K (45 °C), sampling interval is 0.01 s, model type is `block` |
| `example.materials` | Material properties |

### Raw outputs (in `examples/example1/outputs/`)

| File | Meaning |
|---|---|
| `gcc.steady` | Steady-state temperature per node, in Kelvin |
| `gcc.ttrace` | Transient temperature per block per time step, in Kelvin |

`gcc.steady` also lists package nodes (`iface_*`, `hsp_*`, `hsink_*`, `inode_*`). These are the
thermal interface, heat spreader and heatsink layers, not functional blocks.

## 5. Converting to CSV and plots

```bash
cd ~/projects/HotSpot/examples/example1
python3 ../../analysis/analyze_example1.py outputs
```

`setup/example1/run_example1.sh` does the whole pipeline in one go (re-run HotSpot, convert, copy the
results into `setup/example1/results/`). From PowerShell:

```powershell
wsl -d Ubuntu -- bash -c "cd <path-to-repo> && bash setup/example1/run_example1.sh"
```

Files produced (temperatures converted to °C):

| File | Contents |
|---|---|
| `steady.csv` | `node, temp_K, temp_C, is_block` |
| `ttrace.csv` | `step, time_s, <one column per block>` |
| `steady_blocks.png` | Bar chart of steady-state temperature per functional block |
| `ttrace.png` | Transient temperature of the 5 hottest blocks plus the chip-wide maximum |

## 6. What the example1 results show

- Hottest block at steady state: `IntReg_1`, about 69.9 °C. `IntReg_0` is next, then `LdStQ`,
  `Dcache` and `IntExec`.
- Coolest block: `L2`, about 50.7 °C. The L2 cache and FP map blocks are the coolest.
- Transient run: 100 steps of 0.01 s (1 s total). The chip-wide maximum is 78.8 °C in the very
  first sample, then settles to about 69-70.5 °C. The first sample likely reflects a high-power
  first row in `gcc.ptrace`. I did not check this against the trace row by row.
- Results are for the stock example inputs only. They say nothing about your own design yet.

## 7. Suggested next steps

1. Put the project under git (this folder is not a repository yet). Track configs, floorplans,
   power traces and scripts. Keep generated outputs out of version control.
2. Write a driver that takes (config, floorplan, ptrace, options), runs HotSpot, and saves
   everything into a named run folder along with the exact command used.
3. Generalize `analyze_example1.py` so it works on any run folder, and add a sweep script
   for parameter studies.
4. Try the other examples (`example2` to `example6`) for grid models, 3D stacks and microfluidic
   cooling.
