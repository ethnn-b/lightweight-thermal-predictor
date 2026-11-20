"""floorplans.py: load the floorplans we simulate.

A Floorplan bundles everything HotSpot needs for one chip: the power-layer .flp, the .lcf layer
stack, and the list of blocks. Three sources:
  - the TA sample dataset (data/sample_dataset/2D_floorplans/Style_k/fp_XXX), loaded as-is;
  - plain .flp files (HET-A, HOM-16, EV6), for which we write a TA-style two-layer .lcf
    (silicon 150 um + TIM 20 um) so that every floorplan runs with the same grid model.
Names: TA floorplans are called "s<style>_fp<nnn>", e.g. s4_fp003.
"""
from dataclasses import dataclass, field
from pathlib import Path
import shutil

import numpy as np

REPO = Path(__file__).resolve().parents[2]
TA_DIR = REPO / "data" / "sample_dataset" / "2D_floorplans"
FLOORPLAN_DIR = REPO / "floorplans"

# TA layer stack (identical in all 23 TA 2D floorplans)
SILICON = dict(cap=1.75e6, res=0.01, thick=0.00015)
TIM = dict(cap=4e6, res=0.25, thick=2.0e-05)

# Power by block type, as power density (W/mm²) so it also fits floorplans with other core sizes.
# On the TA cores (big 16 mm², little 4 mm²) this is exactly the TA README ranges:
# big 10-20 W, little 5-10 W, and the TA nominal values big 20 W, little 8 W.
DENSITY_RANGE = {"big": (0.625, 1.25), "little": (1.25, 2.5), "L2": (0.05, 0.2),
                 "NoC": (0.05, 0.2), "other": (0.05, 1.0)}
DENSITY_NOMINAL = {"big": 1.25, "little": 2.0, "L2": 0.1, "NoC": 0.1, "other": 0.5}


@dataclass
class Block:
    name: str
    w: float   # metres
    h: float
    x: float   # left
    y: float   # bottom

    @property
    def area(self):
        return self.w * self.h


def read_flp(path):
    blocks = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, w, h, x, y = line.split()[:5]
        blocks.append(Block(name, float(w), float(h), float(x), float(y)))
    return blocks


def classify(block):
    """big / little / fill / other, from the block's name and size."""
    if block.name.startswith("FILL"):
        return "fill"
    n = block.name.lower()
    if n.startswith("big"):
        return "big"
    if n.startswith("little"):
        return "little"
    if n == "l2":
        return "L2"
    if n == "noc":
        return "NoC"
    if block.name.startswith("Core_"):             # TA naming: Core_<k>_L<layer>
        area_mm2 = block.area * 1e6
        if abs(area_mm2 - 16.0) < 1e-6:
            return "big"
        if abs(area_mm2 - 4.0) < 1e-6:
            return "little"
    return "other"


@dataclass
class Floorplan:
    name: str
    dir: Path                 # folder with .flp/.lcf (HotSpot is run on copies of these)
    flp: Path                 # power layer
    lcf: Path
    extra_files: list = field(default_factory=list)   # other files the .lcf refers to
    blocks: list = field(default_factory=list)
    style: str = ""

    def __post_init__(self):
        if not self.blocks:
            self.blocks = read_flp(self.flp)
        # read the input files once; reading /mnt/c from many WSL processes at once is slow
        self._texts = {Path(f).name: Path(f).read_text().replace("\r\n", "\n")
                       for f in [self.flp, self.lcf, *self.extra_files]}

    # --- block bookkeeping -------------------------------------------------
    @property
    def names(self):
        """All blocks of the power layer, in .flp order (= HotSpot output order)."""
        return [b.name for b in self.blocks]

    @property
    def types(self):
        return [classify(b) for b in self.blocks]

    @property
    def power_idx(self):
        """Indices (into names) of blocks that can dissipate power (everything but FILL)."""
        return [i for i, t in enumerate(self.types) if t != "fill"]

    @property
    def power_names(self):
        return [self.names[i] for i in self.power_idx]

    @property
    def power_types(self):
        return [self.types[i] for i in self.power_idx]

    @property
    def n_power(self):
        return len(self.power_idx)

    @property
    def die(self):
        """(width, height) in metres."""
        return (max(b.x + b.w for b in self.blocks), max(b.y + b.h for b in self.blocks))

    def full_power(self, p):
        """Expand a power vector over the power blocks to all blocks (FILL = 0 W)."""
        full = np.zeros(len(self.blocks))
        full[self.power_idx] = p
        return full

    @property
    def power_areas_mm2(self):
        return np.array([self.blocks[i].area * 1e6 for i in self.power_idx])

    def nominal_power(self):
        return np.array([DENSITY_NOMINAL[t] for t in self.power_types]) * self.power_areas_mm2

    def max_power(self):
        return self.power_bounds()[1]

    def power_bounds(self):
        a = self.power_areas_mm2
        lo = np.array([DENSITY_RANGE[t][0] for t in self.power_types]) * a
        hi = np.array([DENSITY_RANGE[t][1] for t in self.power_types]) * a
        return lo, hi

    def copy_inputs(self, dst):
        """Copy the .flp/.lcf files into a run folder (LF endings) and return the local names."""
        for name, text in self._texts.items():
            (Path(dst) / name).write_text(text)
        return self.flp.name, self.lcf.name


def ta_floorplans(styles=(1, 2, 3, 4)):
    """All TA 2D floorplans, in style order."""
    out = []
    for s in styles:
        for d in sorted((TA_DIR / f"Style_{s}").glob("fp_*")):
            fid = d.name
            out.append(Floorplan(name=f"s{s}_{fid.replace('_', '')}", dir=d,
                                 flp=d / f"{fid}_layer_0.flp", lcf=d / f"{fid}.lcf",
                                 extra_files=[d / f"{fid}_tim.flp"], style=f"Style_{s}"))
    return out


def get(name):
    """Floorplan by name: 's4_fp003', 'het_a', 'hom_16' or 'ev6'."""
    if name.startswith("s") and "_fp" in name:
        style, fid = name.split("_")
        for fp in ta_floorplans((int(style[1:]),)):
            if fp.name == name:
                return fp
        raise KeyError(name)
    return plain_floorplan(name)


MAIN_SUBSET = ["s1_fp001", "s2_fp004", "s3_fp002", "s4_fp001"]   # docs/plan.md §4.1


def from_folder(d):
    """Any TA-style folder: one *.lcf, one *_layer_0.flp, and the other files it refers to."""
    d = Path(d)
    lcf = next(d.glob("*.lcf"))
    flp = next(d.glob("*_layer_0.flp"))
    extra = [f for f in d.glob("*.flp") if f != flp]
    return Floorplan(name=d.name, dir=d, flp=flp, lcf=lcf, extra_files=extra, style="folder")


def write_ta_style_lcf(flp_path, out_dir, stem):
    """Write a TA-style two-layer stack (silicon + TIM) for a plain .flp."""
    out_dir = Path(out_dir)
    blocks = read_flp(flp_path)
    die_w = max(b.x + b.w for b in blocks)
    die_h = max(b.y + b.h for b in blocks)
    flp_dst = out_dir / f"{stem}_layer_0.flp"
    shutil.copy(flp_path, flp_dst)
    tim = out_dir / f"{stem}_tim.flp"
    tim.write_text(f"TIM_Top {die_w:.6f} {die_h:.6f} 0.000000 0.000000\n")
    lcf = out_dir / f"{stem}.lcf"
    lcf.write_text(
        "# Layer 0: Silicon\n0\nY\nY\n"
        f"{SILICON['cap']:g}\n{SILICON['res']:g}\n{SILICON['thick']:g}\n{flp_dst.name}\n\n"
        "# Layer 1: TIM\n1\nY\nN\n"
        f"{TIM['cap']:g}\n{TIM['res']:g}\n{TIM['thick']:g}\n{tim.name}\n")
    return flp_dst, lcf, tim


def plain_floorplan(name):
    """HET-A / HOM-16 (floorplans/) or EV6 (HotSpot example1), with a TA-style .lcf."""
    src = {"ev6": REPO / "HotSpot" / "examples" / "example1" / "ev6.flp"}.get(
        name, FLOORPLAN_DIR / f"{name}.flp")
    out = REPO / "floorplans" / "stacks" / name
    out.mkdir(parents=True, exist_ok=True)
    flp, lcf, tim = write_ta_style_lcf(src, out, name)
    return Floorplan(name=name, dir=out, flp=flp, lcf=lcf, extra_files=[tim], style="own")
