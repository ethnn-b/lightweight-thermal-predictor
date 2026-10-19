"""flpgen.py: write HotSpot floorplan (.flp) files from a list of rectangles.

Sizes are given in millimetres (easier to read) and written in metres (what HotSpot wants).
Run directly to (re)generate the project's floorplans:  python3 src/sim/flpgen.py
"""
from dataclasses import dataclass
from pathlib import Path

FLOORPLAN_DIR = Path(__file__).resolve().parents[2] / "floorplans"


@dataclass
class Block:
    name: str
    x: float   # left edge, mm
    y: float   # bottom edge, mm
    w: float   # width, mm
    h: float   # height, mm

    @property
    def area(self):
        return self.w * self.h


def check(blocks, die_w, die_h, tol=1e-9):
    """Raise an error if the floorplan isn't valid."""
    names = [b.name for b in blocks]
    if len(names) != len(set(names)):
        raise ValueError("duplicate block names")
    for b in blocks:
        if b.w <= 0 or b.h <= 0:
            raise ValueError(f"{b.name}: size must be positive")
        if b.x < -tol or b.y < -tol or b.x + b.w > die_w + tol or b.y + b.h > die_h + tol:
            raise ValueError(f"{b.name}: outside the die")
    for i, a in enumerate(blocks):
        for b in blocks[i + 1:]:
            dx = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
            dy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
            if dx > tol and dy > tol:
                raise ValueError(f"{a.name} overlaps {b.name}")
    # no overlaps + total area == die area  =>  blocks tile the die with no gaps
    if abs(sum(b.area for b in blocks) - die_w * die_h) > 1e-6:
        raise ValueError("blocks leave gaps in the die")


def write_flp(blocks, path, comment=""):
    die_w = max(b.x + b.w for b in blocks)
    die_h = max(b.y + b.h for b in blocks)
    check(blocks, die_w, die_h)
    with open(path, "w", newline="\n") as f:          # LF endings, HotSpot runs on Linux
        f.write(f"# {comment}\n# die {die_w:g} x {die_h:g} mm\n")
        f.write("# <name>\t<width>\t<height>\t<left-x>\t<bottom-y>  (metres)\n")
        for b in blocks:
            f.write(f"{b.name}\t{b.w/1e3:.6f}\t{b.h/1e3:.6f}\t{b.x/1e3:.6f}\t{b.y/1e3:.6f}\n")


def core_grid(rows, cols, core_w, core_h, x0=0.0, y0=0.0, prefix="Core"):
    """A rows x cols grid of identical cores (used for HOM-16, HOM-64, little clusters)."""
    return [Block(f"{prefix}{r*cols + c}", x0 + c*core_w, y0 + r*core_h, core_w, core_h)
            for r in range(rows) for c in range(cols)]


def het_a():
    return [
        Block("Big0", 0, 2.5, 2, 2.5),
        Block("Big1", 2, 2.5, 2, 2.5),
        *core_grid(2, 2, 1.0, 1.25, x0=4, y0=2.5, prefix="Little"),
        Block("NoC", 0, 2.0, 6, 0.5),
        Block("L2",  0, 0.0, 6, 2.0),
    ]


def hom_16():
    return core_grid(4, 4, 2.0, 2.0)


if __name__ == "__main__":
    FLOORPLAN_DIR.mkdir(exist_ok=True)
    write_flp(het_a(),  FLOORPLAN_DIR / "het_a.flp",  "HET-A: 2 big, 4 little, NoC, L2")
    write_flp(hom_16(), FLOORPLAN_DIR / "hom_16.flp", "HOM-16: 4x4 identical cores")
    print("wrote", FLOORPLAN_DIR / "het_a.flp", "and", FLOORPLAN_DIR / "hom_16.flp")
