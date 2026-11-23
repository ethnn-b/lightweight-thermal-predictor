"""hotspot.py: run HotSpot on a Floorplan and parse what it writes.

Every call gets its own run folder under $LTP_RUNS (default ~/ltp_runs) with the inputs, the
outputs and meta.json, so any number can be traced back. Runs happen inside WSL on the Linux file
system; the HotSpot binary is the patched build from setup/build_hotspot_ltp.sh (6-decimal output,
cached LU factorisation).

    steady(fp, p)                    -> block temperatures (K), optionally the 64x64 map
    transient(fp, P, dt)             -> temperature trace (K), one row per power row
"""
import functools
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import numpy as np

from .floorplans import REPO

HOTSPOT = Path(os.environ.get("LTP_HOTSPOT", Path.home() / "projects" / "HotSpot-ltp" / "hotspot"))
RUNS = Path(os.environ.get("LTP_RUNS", Path.home() / "ltp_runs"))
CONFIGS = REPO / "configs"
AMBIENT = 318.15   # K, from the example1 config


@functools.lru_cache(maxsize=1)
def _git_commit():
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


def write_ptrace(path, names, P):
    P = np.atleast_2d(P)
    with open(path, "w", newline="\n") as f:
        f.write("\t".join(names) + "\n")
        for row in P:
            f.write("\t".join(f"{v:.6f}" for v in row) + "\n")


def read_steady(path):
    """name -> temperature (K) from a .steady file. Grid-model names lose their 'layer_0_' prefix."""
    out = {}
    for line in Path(path).read_text().splitlines():
        name, val = line.split()[:2]
        if name.startswith("layer_0_"):
            name = name[len("layer_0_"):]
        out[name] = float(val)
    return out


def read_ttrace(path):
    lines = Path(path).read_text().splitlines()
    names = lines[0].split()
    return names, np.array([[float(v) for v in l.split()] for l in lines[1:]])


def read_grid_steady(path, rows, cols, layer=0):
    """The rows x cols map of one layer from a -grid_steady_file. Row 0 = top of the die."""
    vals, current = [], None
    for line in Path(path).read_text().splitlines():
        if line.startswith("Layer"):
            current = int(line.split()[1].rstrip(":"))
            continue
        if current == layer:
            vals.append(float(line.split()[1]))
    return np.array(vals).reshape(rows, cols)


def _new_run_dir(group):
    d = RUNS / group / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    d.mkdir(parents=True)
    return d


def _run(cmd, cwd, meta):
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    meta["wall_s"] = time.perf_counter() - t0
    meta["cmd"] = " ".join(cmd).replace(str(Path.home()), "~")   # no user name in the record
    (Path(cwd) / "meta.json").write_text(json.dumps(meta, indent=1))
    if res.returncode != 0:
        raise RuntimeError(f"HotSpot failed in {cwd}:\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")
    return meta["wall_s"]


@functools.lru_cache(maxsize=None)
def _config_text(path):
    return Path(path).read_text().replace("\r\n", "\n")


def _common_cmd(fp, d, config, model, rows, extra):
    flp_name, lcf_name = fp.copy_inputs(d)
    cfg = Path(config) if config else CONFIGS / ("base_grid64.config" if model == "grid"
                                                 else "base_block.config")
    (d / "hs.config").write_text(_config_text(str(cfg)))
    cmd = [str(HOTSPOT), "-c", "hs.config", "-f", flp_name, "-p", "power.ptrace"]
    if model == "grid":
        cmd += ["-model_type", "grid", "-grid_layer_file", lcf_name,
                "-grid_rows", str(rows), "-grid_cols", str(rows)]
    else:
        # block model has no layer file; give it the TA silicon properties
        cmd += ["-model_type", "block", "-k_chip", "100", "-p_chip", "1.75e6", "-t_chip", "0.00015"]
    for k, v in (extra or {}).items():
        cmd += [f"-{k}", str(v)]
    return cmd, cfg


def steady(fp, p, group="scratch", model="grid", rows=64, grid_map=False, config=None,
           extra=None, keep=True, meta=None):
    """Steady-state temperatures for power vector p over fp.power_names (or all blocks).

    Returns dict(T=array over fp.names (K), wall_s=..., dir=..., grid=map or None).
    """
    p = np.asarray(p, float)
    full = fp.full_power(p) if p.size == fp.n_power else p
    d = _new_run_dir(group)
    cmd, cfg = _common_cmd(fp, d, config, model, rows, extra)
    write_ptrace(d / "power.ptrace", fp.names, full)
    cmd += ["-steady_file", "out.steady"]
    if grid_map and model == "grid":
        cmd += ["-grid_steady_file", "out.grid.steady"]
    m = dict(kind="steady", floorplan=fp.name, model=model, rows=rows, config=cfg.name,
             git=_git_commit(), **(meta or {}))
    wall = _run(cmd, d, m)
    s = read_steady(d / "out.steady")
    out = dict(T=np.array([s[n] for n in fp.names]), wall_s=wall, dir=str(d),
               package={k: v for k, v in s.items() if k not in fp.names})
    if grid_map and model == "grid":
        out["grid"] = read_grid_steady(d / "out.grid.steady", rows, rows)
    if not keep:
        _cleanup(d)
    return out


def transient(fp, P, dt, group="scratch", model="grid", rows=64, init=None, config=None,
              extra=None, keep=True, meta=None):
    """Temperature trace for power trace P (K x n_power, or K x all blocks), step dt seconds.

    HotSpot starts every node at the ambient temperature (cold chip) unless `init` is the path of
    a .steady file. Row k of the result is the temperature at the end of step k.
    Returns dict(T=K x len(fp.names) array (K), wall_s=..., dir=...).
    """
    P = np.atleast_2d(np.asarray(P, float))
    if P.shape[1] == fp.n_power:
        P = np.array([fp.full_power(r) for r in P])
    d = _new_run_dir(group)
    cmd, cfg = _common_cmd(fp, d, config, model, rows, extra)
    write_ptrace(d / "power.ptrace", fp.names, P)
    cmd += ["-sampling_intvl", repr(float(dt)), "-o", "out.ttrace"]
    if init is not None:
        Path(d / "init.steady").write_text(Path(init).read_text())
        cmd += ["-init_file", "init.steady"]
    m = dict(kind="transient", floorplan=fp.name, model=model, rows=rows, dt=dt, steps=len(P),
             config=cfg.name, git=_git_commit(), **(meta or {}))
    wall = _run(cmd, d, m)
    names, T = read_ttrace(d / "out.ttrace")
    order = [names.index(n) for n in fp.names]
    out = dict(T=T[:, order], wall_s=wall, dir=str(d))
    if not keep:
        _cleanup(d)
    return out


def _cleanup(d):
    for f in Path(d).iterdir():
        if f.name != "meta.json":
            f.unlink()
