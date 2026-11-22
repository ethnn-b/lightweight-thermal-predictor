"""Demo step 2: generate brand-new power inputs for a demo floorplan.

    python3 demo/new_power.py demo/output/<floorplan> [--steps 2000]

Writes, in HotSpot's .ptrace format (one column per block, watts; FILL blocks 0 W):
  steady_power.ptrace      one row: a random power for each core, within its range
                           (big 10-20 W, little 5-10 W)
  transient_power.ptrace   --steps rows of 1 ms: every core switches between 4 power levels
                           at random times, independently of the others
and 2_power_trace.png. The seed is the floorplan's, so the same folder always gets the same power.
"""
import argparse
from pathlib import Path

import numpy as np

from run_demo import H, new_power, plot_power, plt, steady_power_figure
from src.sim.floorplans import from_folder

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("folder", help="the floorplan folder from step 1")
ap.add_argument("--steps", type=int, default=2000, help="transient length in 1 ms steps (default 2000)")
a = ap.parse_args()
d = Path(a.folder)
fp = from_folder(d)
seed = int(fp.name.rsplit("_", 1)[1])

p, P = new_power(fp, seed, a.steps)
H.write_ptrace(d / "steady_power.ptrace", fp.names, fp.full_power(p))
H.write_ptrace(d / "transient_power.ptrace", fp.names, np.array([fp.full_power(r) for r in P]))
names = [n.replace("_L0", "") for n in fp.power_names]
print(f"steady power ({p.sum():.1f} W in total) -> steady_power.ptrace")
for n, t, x in zip(names, fp.power_types, p):
    print(f"  {n:7s} {t:6s} {x:5.1f} W")
print(f"transient power: {a.steps} steps of 1 ms ({a.steps / 1000:g} s), {P.sum(1).min():.0f}-"
      f"{P.sum(1).max():.0f} W in total, {int((np.diff(P, axis=0) != 0).any(1).sum())} power changes "
      f"-> transient_power.ptrace")
fig, ax = plt.subplots(figsize=(8, 3.6), layout="constrained")
plot_power(ax, fp, P)
fig.savefig(d / "2_power_trace.png")
plt.close(fig)
fig = steady_power_figure(fp, p)
fig.savefig(d / "2_steady_power.png")
print("  plots -> 2_steady_power.png, 2_power_trace.png")
