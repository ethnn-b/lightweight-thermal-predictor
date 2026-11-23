"""Figure for the Stage 4 report: the top panel of run.py's trace_example.png only (no error panel).

Reads the cached traces and calibration runs of run.py ($LTP_RUNS); no new HotSpot runs.
    PYTHONPATH=.:experiments python3 experiments/P3-1_transient_predictor/plot_stage4.py
"""
import numpy as np

from common import plt
from src.sim import floorplans as F, datasets
from src.ltp import calibrate as C
from run import OUT, DT, CAL_STEPS, ARX_ORDER, build_models, predict


def main():
    fp = F.get("s1_fp001")
    cal = C.run_calibration_runs_many([fp])[fp.name]
    test, ct = datasets.traces_many([(fp, "phase", 10000, "test0"),
                                     (fp, "excitation", 60000, "cal")], dt=DT)
    P, T = test["P"], test["T"]
    models = build_models(fp, cal, dict(P=ct["P"][:CAL_STEPS], T=ct["T"][:CAL_STEPS]))
    k = fp.power_idx[int(np.argmax(T[-1, fp.power_idx]))]
    tt = np.arange(1, len(P) + 1) * DT
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.plot(tt, T[:, k] - 273.15, "k", lw=1.5, label="HotSpot")
    for n in ["T1", "T3 M=2", "T3 M=4", f"T2 ARX{ARX_ORDER}"]:
        ax.plot(tt, predict(models[n], fp, P)[:, k] - 273.15, lw=0.8, label=n)
    ax.set(xlabel="time (s)", ylabel="°C", title=f"{fp.name}, {fp.names[k]}: 10 s test trace from a cold chip")
    ax.legend(fontsize=7, ncol=5)
    fig.savefig(OUT / "trace_example_stage4.png")


if __name__ == "__main__":
    main()
