"""stepper.py: HotSpot as a closed-loop 'chip' (plan.md P6-1).

DTM needs a plant whose power can change every interval in response to its temperature. HotSpot's
transient mode reads a power trace row by row, so we give it a pipe instead of a file: each call
to step(p) writes one power row and reads back the temperature row HotSpot computes for it. The
grid model keeps its full internal state (all cells, spreader, sink) between steps, exactly as
in an ordinary transient run. Needs the patched build (it flushes every output row).

    with HotSpotStepper(fp, dt=1e-3) as chip:
        T = chip.step(p)          # block temperatures (K) at the end of this interval
"""
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import hotspot as H


class HotSpotStepper:
    def __init__(self, fp, dt, rows=64, config=None, init=None):
        """init: path of a .steady file to start from (HotSpot -init_file); default cold chip."""
        self.fp, self.dt = fp, dt
        H.RUNS.mkdir(parents=True, exist_ok=True)
        self.dir = Path(tempfile.mkdtemp(prefix="stepper_", dir=H.RUNS))
        cmd, _ = H._common_cmd(fp, self.dir, config, "grid", rows, None)
        fifo = self.dir / "out.fifo"
        os.mkfifo(fifo)
        i = cmd.index("power.ptrace")
        cmd[i] = "/dev/stdin"
        cmd += ["-sampling_intvl", repr(float(dt)), "-o", str(fifo)]
        if init is not None:
            (self.dir / "init.steady").write_text(Path(init).read_text())
            cmd += ["-init_file", "init.steady"]
        self.proc = subprocess.Popen(cmd, cwd=self.dir, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        self.proc.stdin.write("\t".join(fp.names) + "\n")
        self.proc.stdin.flush()
        self.out = open(fifo)
        names = self.out.readline().split()
        self.order = [names.index(n) for n in fp.names]
        self.k = 0

    def step(self, p):
        p = np.asarray(p, float)
        full = self.fp.full_power(p) if p.size == self.fp.n_power else p
        self.proc.stdin.write("\t".join(f"{v:.6f}" for v in full) + "\n")
        self.proc.stdin.flush()
        line = self.out.readline()
        if not line:
            raise RuntimeError("HotSpot stepper stopped")
        self.k += 1
        return np.array([float(v) for v in line.split()])[self.order]

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=60)
        except Exception:
            self.proc.kill()
        self.out.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
