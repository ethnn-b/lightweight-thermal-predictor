# Lightweight Temperature Predictor (TapaSense): calibrate once, predict fast

Computer Architecture course project, topic *thermal management: lightweight temperature predictor*.
Ethan Bobby Kurien and Kaivalya Mase.

## The problem

Dynamic thermal management (DTM) needs core temperatures every millisecond, and ideally a few
milliseconds ahead. The HotSpot simulator computes them accurately but is slow: 0.24 s per
steady-state answer and about 5.5 ms per 1 ms transient step.

The task: build a predictor in two stages.

1. **Calibration** (once per floorplan with heterogeneous cores): run HotSpot a few times and fit
   a small set of coefficients.
2. **Prediction**: from those coefficients alone, give steady-state or transient temperatures for
   any power input.

Metrics: accuracy, prediction time, model size. Wishlist: show that it helps proactive DTM.

## What we built

HotSpot without leakage is linear in power, so the models are exact or nearly exact:

- **Calibration**: 8 HotSpot runs per floorplan for the steady model, 24 for steady and transient
  (1 W in one core at a time).
- **S1 (steady)**: an influence matrix *G*, so that T = T_amb + G·P. Exact to 3×10⁻⁵ K, 2.6 µs
  per prediction, under 1 kB, about 90,000× faster than HotSpot. **S1-hot-max** also predicts
  the hottest cell inside each core.
- **T3 (transient)**: a sum of exponentials (M = 4) fitted to the step responses.
  0.06–0.09 K mean error and 0.3 K worst, 3 µs per 1 ms step (about 1,800× faster than
  HotSpot), about 4 kB. It can also forecast a few milliseconds ahead from measured temperatures.
- **DTM**: proactive DTM driven by T3 forecasts spends 60–130× less time above the limit than
  reactive DTM, for a 1–1.6 % loss in throughput.

Every steady and transient target in our scorecard was met. The one exception is calibration
time, which is about 2.75 min against a 2 min target. Results were checked on the TAs' 23
floorplans and on floorplans generated afterwards: 500 for the steady predictor and 100 for the
transient one. The full scorecard is in
[`reports/stage4.tex`](reports/stage4.tex).

## Repository layout

| Path | Contents |
|---|---|
| [`src/ltp/`](src/ltp/) | **The product**: models (S1, S2, T1, T2, T3), calibration, `Predictor`, command line |
| [`src/sim/`](src/sim/) | HotSpot runner and parser, floorplan loader and generators, power generators, closed-loop stepper |
| [`experiments/`](experiments/) | One folder per experiment (P0–P6): `run.py`, `README.md` with findings, `results/`. The [index](experiments/README.md) gives a one-line result for each |
| [`demo/`](demo/) | Live demo: a new floorplan and new power, HotSpot vs S1 / T3 maps |
| [`tests/`](tests/) | Unit tests for the models |
| [`data/`](data/) | `sample_dataset/`: TA floorplans (big/little power fixed for Style_2). `generated/`: our TA-style floorplans. `generated_traces/`: calibration and test power traces |
| [`floorplans/`](floorplans/), [`configs/`](configs/) | Our own floorplans (HET-A, HOM-16/64, TA-style stacks) and the base HotSpot configs |
| [`setup/`](setup/) | Script and patch for our faster HotSpot build. `example1/` is the first HotSpot sanity run (P0-1) |
| [`HotSpot/`](HotSpot/) | HotSpot source (git submodule, unmodified) |
| [`docs/`](docs/) | Documentation (see below) |
| [`reports/`](reports/) | Scope document and the Stage 2, 3 and 4 reports (LaTeX and PDF) |
| [`presentations/`](presentations/) | Final presentation (Beamer) |

### Documentation

| File | What it is |
|---|---|
| [`docs/guide.html`](docs/guide.html) | **Start here.** A beginner-friendly guide to every experiment and its results (open it in a browser) |
| [`docs/plan.md`](docs/plan.md) | Project plan: models, targets, experiments, status |
| [`docs/hotspot_for_dummies.md`](docs/hotspot_for_dummies.md) | Concepts from scratch (why chips get hot, up to proactive DTM), and a walk-through of each experiment |
| [`docs/literature_review_and_references.md`](docs/literature_review_and_references.md) | Prior work and where each model comes from |
| [`docs/dataset.md`](docs/dataset.md) | The TAs' dataset and the two papers they pointed to |
| [`docs/setup.md`](docs/setup.md) | WSL and HotSpot setup, and the example1 run |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Dated log of who did what |

## Try the predictor yourself

Calibration runs HotSpot, a Linux program, so you need Linux or WSL (Ubuntu) on Windows, and this
repository. Prediction itself needs only NumPy and the model file that calibration writes.

1. **Windows only: install WSL.** In PowerShell as administrator, run `wsl --install -d Ubuntu`,
   restart, and open "Ubuntu". Run every later step in that Ubuntu terminal.
2. **Install the tools** (compiler, HotSpot's solver libraries, Python packages):
   ```bash
   sudo apt update
   sudo apt install -y git build-essential libsuperlu-dev libblas-dev python3-numpy python3-scipy python3-matplotlib
   ```
3. **Download this repository together with HotSpot** (into the Linux home folder, where file
   access is fast):
   ```bash
   cd ~
   git clone --recurse-submodules https://github.com/ethnn-b/lightweight-thermal-predictor.git
   cd lightweight-thermal-predictor
   ```
4. **Build our patched HotSpot** (once, about a minute; it prints 6 decimals instead of 2):
   ```bash
   HOTSPOT_SRC=$PWD/HotSpot bash setup/build_hotspot_ltp.sh
   ```
5. **Calibrate** on one of the TA floorplans (24 HotSpot runs, a few minutes):
   ```bash
   python3 -m src.ltp calibrate s4_fp001 -o model.npz
   ```
6. **Predict** steady temperatures for any power per core (W, cores in order Core_0..Core_7), or
   temperatures over time for a power trace:
   ```bash
   python3 -m src.ltp steady model.npz --power 20,20,8,8,8,8,8,8
   python3 -m src.ltp transient model.npz --ptrace data/sample_dataset/2D_floorplans/Style_4/fp_001/fp_001_transient.ptrace -o out.ttrace
   ```
7. **Check it against HotSpot** (accuracy, time per prediction, model size):
   ```bash
   python3 -m src.ltp bench model.npz s4_fp001
   ```
8. **Or run the whole demo** on a floorplan nobody has seen: a new floorplan and power, HotSpot,
   calibration, prediction and comparison plots in `demo/output/<name>/`:
   ```bash
   bash demo/run_demo.sh --style 4 --seed 2615
   ```

Once you have a `model.npz`, prediction works anywhere with Python and NumPy, without HotSpot or
the rest of the repository: copy `model.npz` and [`src/ltp/predictor.py`](src/ltp/predictor.py)
and use `Predictor` as shown below.

## Quick start (for developers)

Everything runs in WSL (Ubuntu) from the repo root, after steps 1–4 above.

```bash
python3 tests/test_models.py                # unit tests
bash experiments/run.sh P2-1_steady_predictor   # rerun any experiment
```

From Python:

```python
from src.ltp.predictor import Predictor     # or `from predictor import Predictor` with the copied file
p = Predictor.load("model.npz")
T = p.steady([20, 20, 8, 8, 8, 8, 8, 8])     # kelvin, every block
T_t = p.transient(P_trace, dt=1e-3)          # P_trace: one row of core powers (W) per 1 ms step
```

HotSpot runs and calibrations are cached in `~/ltp_runs/` inside WSL, so reruns only redo the
analysis. More commands are in
[`experiments/P5-1_ltp_package/README.md`](experiments/P5-1_ltp_package/README.md).

## Experiments at a glance

| Phase | Experiments | Question |
|---|---|---|
| P0 | linearity, block vs grid, infrastructure, TA floorplans | Can we trust HotSpot as the reference, and make it fast? |
| P1 | step calibration, trace calibration, is calibration needed? | How few HotSpot runs fit the model? |
| P2 | steady predictor, layout effects, hot spots | How accurate, fast and small is S1? |
| P3 | transient predictor, forecast horizon, Pareto, exact state space (T4) | How accurate, fast and small is T3? |
| P4 | robustness, recalibration, leakage | Where does it break? |
| P5 | `ltp` package | Can someone else use it? |
| P6 | closed-loop HotSpot, reactive vs proactive DTM, core selection | Does it help DTM? |

Headline numbers for each experiment are in [`experiments/README.md`](experiments/README.md).
