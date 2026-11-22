"""Demo step 1: generate a brand-new floorplan in one of the TA styles.

    python3 demo/new_floorplan.py [--style 1-4] [--seed N]

Writes demo/output/demo_s<style>_<seed>/ with the TA file set (<name>_layer_0.flp, <name>_tim.flp,
<name>.lcf) and 1_floorplan.png. Every later step works on that folder.
"""
import argparse
import time

from run_demo import DEMO, STYLE_TEXT, new_floorplan, pick_style, plot_floorplan, plt

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--style", type=int, choices=[1, 2, 3, 4], help="TA style (default: drawn from the seed)")
ap.add_argument("--seed", type=int, help="seed of the random layout (default: a new one)")
a = ap.parse_args()
seed = a.seed if a.seed is not None else int(time.time()) % 100000
style = pick_style(a.style, seed)

d = DEMO / "output" / f"demo_s{style}_{seed}"
fp = new_floorplan(style, seed, d)
W, H = fp.die
print(f"new floorplan {fp.name}")
print(f"  Style_{style}: {STYLE_TEXT[style]}")
print(f"  die {W * 1e3:g} x {H * 1e3:g} mm, {fp.n_power} cores "
      f"({fp.power_types.count('big')} big 4x4 mm, {fp.power_types.count('little')} little 2x2 mm), "
      f"{len(fp.names) - fp.n_power} FILL blocks for the empty silicon")
fig, ax = plt.subplots(figsize=(5, 5 * H / W + 0.6), layout="constrained")
plot_floorplan(ax, fp)
fig.savefig(d / "1_floorplan.png")
print(f"  files: {d.relative_to(DEMO.parent)}/")
for f in sorted(d.glob(f"{fp.name}*")) + [d / "1_floorplan.png"]:
    print(f"    {f.name}")
