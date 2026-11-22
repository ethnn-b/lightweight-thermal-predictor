"""Plot the steady power of a demo folder (reads its steady_power.ptrace).

    python3 demo/plot_steady_power.py demo/output/<floorplan>

Writes 2_steady_power.png: power per core against its allowed range, and painted on the floorplan.
"""
import sys
from pathlib import Path

from run_demo import plt, steady_power_figure
from src.ltp.cli import _read_ptrace
from src.sim.floorplans import from_folder

d = Path(sys.argv[1])
fp = from_folder(d)
p = _read_ptrace(d / "steady_power.ptrace", fp.power_names)[0]
fig = steady_power_figure(fp, p)
fig.savefig(d / "2_steady_power.png")
plt.close(fig)
print(f"{p.sum():.1f} W in total -> {d / '2_steady_power.png'}")
