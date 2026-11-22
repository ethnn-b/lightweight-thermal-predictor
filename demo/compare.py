"""Demo step 6: compare HotSpot's outputs with the predictor's, and draw the temperature maps.

    python3 demo/compare.py demo/output/<floorplan> [--grid-ttrace /tmp/hotspot.grid.ttrace]

Reads the files written in the earlier steps of the folder:
  hotspot.steady, hotspot.grid.steady       HotSpot steady: block temperatures, 64 x 64 map
  hotspot.ttrace, --grid-ttrace             HotSpot transient: block temperatures every step,
                                            64 x 64 map every step (only the last one is used)
  s1.steady, t3.ttrace, model.npz           the predictor's outputs and the model file
and writes 3_steady_maps.png, 4_transient_maps_end.png, 5_transient_over_time.png, cores.csv and
summary.txt. Prediction times are measured here with the same model file.
"""
import argparse
from pathlib import Path

import numpy as np

from run_demo import (AMB, DT, K2C, ROWS, H, bench, label, last_grid, over_time_figure, plt,
                      steady_figure, transient_figure, write_csv)
from src.ltp.cli import _read_ptrace
from src.ltp.predictor import Predictor
from src.sim.floorplans import from_folder
from src.sim.gridmap import hotspot_weights

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("folder")
ap.add_argument("--grid-ttrace", default="/tmp/hotspot.grid.ttrace",
                help="HotSpot's -grid_transient_file from step 3")
a = ap.parse_args()
d = Path(a.folder)
fp = from_folder(d)
core = fp.power_idx
names_c = [label(fp, i) for i in core]


def by_name(path):
    """A HotSpot-style table (header of block names, rows of kelvin) in the floorplan's block order."""
    names, T = H.read_ttrace(path)
    return T[:, [names.index(n) for n in fp.names]]


# HotSpot
st = H.read_steady(d / "hotspot.steady")
hs_T = np.array([st[n] for n in fp.names])
hs_grid = H.read_grid_steady(d / "hotspot.grid.steady", ROWS, ROWS)
hs_Tt = by_name(d / "hotspot.ttrace")
hs_grid_end = last_grid(a.grid_ttrace)
chk = np.abs(hotspot_weights(fp, ROWS, ROWS) @ hs_grid_end.ravel() - hs_Tt[-1]).max()
if chk > 1e-3:
    raise SystemExit(f"{a.grid_ttrace} does not belong to this run: its last map differs from the last "
                     f"row of hotspot.ttrace by {chk:.3f} K. Rerun the HotSpot transient command.")

# predictor
s1_T = by_name(d / "s1.steady")[0]
t3_Tt = by_name(d / "t3.ttrace")
if len(t3_Tt) != len(hs_Tt):
    raise SystemExit(f"t3.ttrace has {len(t3_Tt)} steps, hotspot.ttrace {len(hs_Tt)}")
pred = Predictor.load(d / "model.npz")
p = _read_ptrace(d / "steady_power.ptrace", pred.power_names)[0]
P = _read_ptrace(d / "transient_power.ptrace", pred.power_names)
s1_t = bench.time_call(pred.steady, [(p,)])[0]                # median of 10,000 calls
t3_t = bench.time_per_step(pred.transient, P, DT)             # per step, median of 5 runs

e_s = s1_T[core] - hs_T[core]
e_end = t3_Tt[-1, core] - hs_Tt[-1, core]
e_all = t3_Tt[:, core] - hs_Tt[:, core]
steps = len(hs_Tt)

fig = steady_figure(fp, hs_grid, hs_T, s1_T, f"Steady state, {fp.name}, {p.sum():.1f} W: HotSpot vs S1")
fig.savefig(d / "3_steady_maps.png"); plt.close(fig)
fig = transient_figure(fp, hs_grid_end, hs_Tt[-1], t3_Tt[-1],
                       f"Transient, end of the trace (t = {steps * DT:g} s, cold start), {fp.name}: "
                       f"HotSpot vs T3 (M = 4)")
fig.savefig(d / "4_transient_maps_end.png"); plt.close(fig)
fig = over_time_figure(fp, hs_Tt, t3_Tt)
fig.savefig(d / "5_transient_over_time.png"); plt.close(fig)

write_csv(d / "cores.csv", [dict(core=names_c[j], steady_power_W=round(p[j], 3),
                                 steady_HotSpot_C=round(hs_T[i] - K2C, 6), steady_S1_C=round(s1_T[i] - K2C, 6),
                                 steady_error_K=f"{s1_T[i] - hs_T[i]:.2e}", end_power_W=round(P[-1, j], 3),
                                 end_HotSpot_C=round(hs_Tt[-1, i] - K2C, 4), end_T3_C=round(t3_Tt[-1, i] - K2C, 4),
                                 end_error_K=round(t3_Tt[-1, i] - hs_Tt[-1, i], 4))
                            for j, i in enumerate(core)])

rows = "\n".join(f"  {names_c[j]:7s} {hs_T[i] - K2C:9.4f} {s1_T[i] - K2C:9.4f} {e_s[j]:+9.1e}"
                 f"     {hs_Tt[-1, i] - K2C:9.3f} {t3_Tt[-1, i] - K2C:9.3f} {e_end[j]:+7.3f}"
                 for j, i in enumerate(core))
hot = lambda T: f"{names_c[int(np.argmax(T[core]))]} at {T[core].max() - K2C:.2f} C"  # noqa: E731
summary = f"""{fp.name}: core temperatures (C)
               steady state                          end of transient (t = {steps * DT:g} s)
  core      HotSpot        S1     error (K)     HotSpot        T3  error (K)
{rows}

  hottest core, steady:     HotSpot {hot(hs_T)}, S1 {hot(s1_T)}
  hottest core, transient:  HotSpot {hot(hs_Tt[-1])}, T3 {hot(t3_Tt[-1])}
  S1: max |error| {np.abs(e_s).max():.1e} K, {s1_t * 1e6:.1f} us per prediction
  T3: max |error| at the end {np.abs(e_end).max():.3f} K; over all {steps} steps mean {np.abs(e_all).mean():.3f} K,
      max {np.abs(e_all).max():.3f} K; {t3_t * 1e6:.1f} us per step ({t3_t * steps * 1e3:.1f} ms for the trace)
  model: {pred.size_bytes()} B of coefficients
  hottest point anywhere (HotSpot 64 x 64 map): steady {hs_grid.max() - K2C:.2f} C, end {hs_grid_end.max() - K2C:.2f} C
"""
(d / "summary.txt").write_text(summary)
print(summary)
print("figures: 3_steady_maps.png, 4_transient_maps_end.png, 5_transient_over_time.png")
