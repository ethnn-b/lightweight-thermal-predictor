"""gridmap.py: relate HotSpot grid cells to floorplan blocks.

HotSpot's grid map has row 0 at the top of the die. A block's temperature in the .steady file
(grid_map_mode avg) is the plain mean of every cell the block touches, partial boundary cells
included with full weight (set_bgmap / xlate_temp_g2b in temperature_grid.c).
"""
import numpy as np


def _tolerant_floor(x, tol=1e-5):
    return int(np.floor(x + tol))


def _tolerant_ceil(x, tol=1e-5):
    return int(np.ceil(x - tol))


def hotspot_weights(fp, rows, cols):
    """W[b, r*cols + c] such that W @ map.ravel() reproduces HotSpot's block temperatures."""
    W_die, H_die = fp.die
    cw, ch = W_die / cols, H_die / rows
    out = np.zeros((len(fp.blocks), rows * cols))
    for k, b in enumerate(fp.blocks):
        i1 = rows - _tolerant_ceil((b.y + b.h) / ch)
        i2 = rows - _tolerant_floor(b.y / ch)
        j1 = _tolerant_floor(b.x / cw)
        j2 = _tolerant_ceil((b.x + b.w) / cw)
        m = np.zeros((rows, cols))
        m[i1:i2, j1:j2] = 1.0
        out[k] = m.ravel() / m.sum()
    return out


def overlap_weights(fp, rows, cols):
    """W[b, r*cols + c] = fraction of block b's area that lies in cell (r, c). Rows sum to 1."""
    W_die, H_die = fp.die
    cw, ch = W_die / cols, H_die / rows
    xs = np.arange(cols + 1) * cw
    ys_top = H_die - np.arange(rows + 1) * ch          # row r spans [ys_top[r+1], ys_top[r]]
    out = np.zeros((len(fp.blocks), rows * cols))
    for i, b in enumerate(fp.blocks):
        ox = np.clip(np.minimum(xs[1:], b.x + b.w) - np.maximum(xs[:-1], b.x), 0, None)
        oy = np.clip(np.minimum(ys_top[:-1], b.y + b.h) - np.maximum(ys_top[1:], b.y), 0, None)
        out[i] = np.outer(oy, ox).ravel() / b.area
    return out


def cell_centres(fp, rows, cols):
    """(x, y) in metres of every cell centre, flattened in the same order as the map."""
    W_die, H_die = fp.die
    x = (np.arange(cols) + 0.5) * W_die / cols
    y = H_die - (np.arange(rows) + 0.5) * H_die / rows
    X, Y = np.meshgrid(x, y)
    return X.ravel(), Y.ravel()


def block_cells(fp, rows, cols, threshold=0.5):
    """For each block, the indices of cells whose centre lies inside it."""
    X, Y = cell_centres(fp, rows, cols)
    return [np.where((X >= b.x) & (X < b.x + b.w) & (Y >= b.y) & (Y < b.y + b.h))[0]
            for b in fp.blocks]
