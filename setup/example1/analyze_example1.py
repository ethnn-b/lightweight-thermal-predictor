"""Convert HotSpot example1 outputs to CSV and plots.

Usage: python3 analyze_example1.py [outputs_dir]
Reads  <outputs_dir>/gcc.steady and gcc.ttrace (temperatures in Kelvin)
Writes steady.csv, ttrace.csv, steady_blocks.png, ttrace.png (temperatures in Celsius)
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

K = 273.15
SAMPLING_INTVL = 0.01  # seconds, from -sampling_intvl in example.config
# Non-silicon nodes HotSpot adds for the package model
PACKAGE_PREFIXES = ("iface_", "hsp_", "hsink_", "inode_")

out = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs")

steady = pd.read_csv(out / "gcc.steady", sep="\t", header=None, names=["node", "temp_K"])
steady["temp_C"] = steady["temp_K"] - K
steady["is_block"] = ~steady["node"].str.startswith(PACKAGE_PREFIXES)
steady.to_csv(out / "steady.csv", index=False)

trace = pd.read_csv(out / "gcc.ttrace", sep="\t")
trace = trace.loc[:, ~trace.columns.str.startswith("Unnamed")]
trace.insert(0, "step", range(len(trace)))
trace.loc[:, trace.columns != "step"] -= K
trace.insert(1, "time_s", trace["step"] * SAMPLING_INTVL)
trace.to_csv(out / "ttrace.csv", index=False)

# Steady state, functional blocks only, sorted
blocks = steady[steady["is_block"]].sort_values("temp_C")
fig, ax = plt.subplots(figsize=(8, 9))
ax.barh(blocks["node"], blocks["temp_C"])
ax.set_xlabel("Steady-state temperature (°C)")
ax.set_xlim(blocks["temp_C"].min() - 2, blocks["temp_C"].max() + 1)
ax.set_title("example1: steady-state temperature per block")
fig.tight_layout()
fig.savefig(out / "steady_blocks.png", dpi=150)

# Transient: 5 hottest blocks by peak temperature, plus chip-wide max
cols = [c for c in trace.columns if c not in ("step", "time_s")]
hottest = trace[cols].max().nlargest(5).index
fig, ax = plt.subplots(figsize=(9, 5))
for c in hottest:
    ax.plot(trace["time_s"], trace[c], label=c)
ax.plot(trace["time_s"], trace[cols].max(axis=1), "k--", label="chip max")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Temperature (°C)")
ax.set_title("example1: transient temperature, hottest blocks")
ax.legend()
fig.tight_layout()
fig.savefig(out / "ttrace.png", dpi=150)

print(f"hottest block (steady): {blocks.iloc[-1]['node']} {blocks.iloc[-1]['temp_C']:.1f} C")
print(f"coolest block (steady): {blocks.iloc[0]['node']} {blocks.iloc[0]['temp_C']:.1f} C")
print(f"transient: {len(trace)} steps, peak {trace[cols].max().max():.1f} C")
