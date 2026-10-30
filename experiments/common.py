"""Shared helpers for experiment scripts.

Each experiment lives in experiments/<ID>_<name>/ with run.py, README.md and results/.
Run from the repo root inside WSL:  python3 experiments/<ID>_<name>/run.py
"""
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"figure.dpi": 120, "savefig.bbox": "tight", "font.size": 9,
                     "axes.grid": True, "grid.alpha": 0.3})


def results_dir(script_file):
    d = Path(script_file).resolve().parent / "results"
    d.mkdir(exist_ok=True)
    return d


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, default=float))


def save_csv(path, rows):
    rows = list(rows)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def md_table(rows, fmt="{:.4g}"):
    """Markdown table from a list of dicts (printed into the experiment log)."""
    rows = list(rows)
    keys = list(rows[0].keys())
    out = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for r in rows:
        out.append("| " + " | ".join(fmt.format(v) if isinstance(v, float) else str(v)
                                     for v in r.values()) + " |")
    return "\n".join(out)
