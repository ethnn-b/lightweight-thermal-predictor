"""P0-5: TA floorplans, power, traces, and a first look at their temperatures.

  (a) load all 23 TA 2D floorplans (+ HET-A) and tag cores big/little by size;
  (b) power generators: random steady vectors and phase-based traces within the TA ranges;
  (c) steady temperatures of every floorplan at TA nominal power and at all-cores-max power;
  (+) the TA's own Style_2 ptraces (big-core power on little cores) vs power assigned by size.
"""
import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, gridmap as GM, powergen
from src.sim.parallel import pmap

OUT = results_dir(__file__)
G = "P0-5"


def run(fp_name, which):
    fp = F.get(fp_name)
    p = {"nominal": fp.nominal_power(), "max": fp.max_power()}[which] if which != "ta_ptrace" \
        else ta_ptrace_power(fp)
    r = H.steady(fp, p, group=G, grid_map=True, keep=False)
    cells = GM.block_cells(fp, 64, 64)
    g = r["grid"].ravel()
    r["hot"] = np.array([g[c].max() if len(c) else np.nan for c in cells])
    del r["grid"]
    return r


def ta_ptrace_power(fp):
    """Power vector exactly as written in the TA's *_steady.ptrace (by block name)."""
    fid = fp.flp.name.split("_layer")[0]
    lines = (fp.dir / f"{fid}_steady.ptrace").read_text().split("\n")
    vals = dict(zip(lines[0].split(), map(float, lines[1].split())))
    return np.array([vals[n] for n in fp.names])


def main():
    fps = F.ta_floorplans() + [F.get("het_a")]
    # (a) inventory
    inv = []
    for fp in fps:
        W, Hd = fp.die
        t = fp.power_types
        inv.append(dict(floorplan=fp.name, style=fp.style, die_mm=f"{W*1e3:g}x{Hd*1e3:g}",
                        n_power=fp.n_power, big=t.count("big"), little=t.count("little"),
                        other=fp.n_power - t.count("big") - t.count("little"),
                        fill=fp.types.count("fill"),
                        core_area_pct=100 * fp.power_areas_mm2.sum() / (W * Hd * 1e6),
                        nominal_W=float(fp.nominal_power().sum())))
    save_csv(OUT / "inventory.csv", inv)

    # (c) nominal and max power, all floorplans
    jobs = [dict(fp_name=fp.name, which=w) for fp in fps for w in ("nominal", "max")]
    style2_bad = ["s2_fp001", "s2_fp002", "s2_fp003", "s2_fp005"]
    jobs += [dict(fp_name=n, which="ta_ptrace") for n in style2_bad]
    res = dict(zip([(j["fp_name"], j["which"]) for j in jobs], pmap(run, jobs)))

    rows = []
    for fp, iv in zip(fps, inv):
        idx = fp.power_idx
        row = dict(floorplan=fp.name, style=fp.style, die_mm=iv["die_mm"],
                   core_area_pct=iv["core_area_pct"])
        for w in ("nominal", "max"):
            T = res[(fp.name, w)]["T"][idx] - 273.15
            hot = res[(fp.name, w)]["hot"][idx] - 273.15
            k = int(np.argmax(T))
            row[f"{w}_peak_core_C"] = float(T.max())
            row[f"{w}_hottest_core"] = f"{fp.power_names[k]} ({fp.power_types[k]})"
            row[f"{w}_peak_cell_C"] = float(hot.max())
            big = [i for i, t in enumerate(fp.power_types) if t == "big"]
            lit = [i for i, t in enumerate(fp.power_types) if t == "little"]
            if big and lit:
                row[f"{w}_mean_big_C"] = float(T[big].mean())
                row[f"{w}_mean_little_C"] = float(T[lit].mean())
        rows.append(row)
    save_csv(OUT / "temperatures.csv", rows)
    short = [{k: r[k] for k in ("floorplan", "die_mm", "core_area_pct", "nominal_peak_core_C",
                                "nominal_hottest_core", "nominal_peak_cell_C", "max_peak_core_C",
                                "max_peak_cell_C")} for r in rows]
    print(md_table(short, "{:.1f}"))

    # (+) Style_2: TA ptrace as given vs power assigned by size
    s2 = []
    for n in style2_bad:
        fp = F.get(n)
        idx = fp.power_idx
        Tg = res[(n, "ta_ptrace")]["T"][idx] - 273.15
        Tn = res[(n, "nominal")]["T"][idx] - 273.15
        s2.append(dict(floorplan=n, ta_ptrace_peak_C=float(Tg.max()),
                       ta_ptrace_peak_cell_C=float(np.nanmax(res[(n, "ta_ptrace")]["hot"][idx]) - 273.15),
                       by_size_peak_C=float(Tn.max()),
                       by_size_peak_cell_C=float(np.nanmax(res[(n, "nominal")]["hot"][idx]) - 273.15)))
    save_csv(OUT / "style2_ptrace_check.csv", s2)
    print(); print(md_table(s2, "{:.1f}"))

    # figures: peak temperature vs white space; big vs little
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
    for st, mk in zip(["Style_1", "Style_2", "Style_3", "Style_4", "own"], "osD^v"):
        rr = [r for r in rows if r["style"] == st]
        ax[0].scatter([r["core_area_pct"] for r in rr], [r["nominal_peak_core_C"] for r in rr],
                      marker=mk, label=st if st != "own" else "HET-A")
        rr = [r for r in rr if "nominal_mean_big_C" in r]
        ax[1].scatter([r["nominal_mean_big_C"] for r in rr], [r["nominal_mean_little_C"] for r in rr],
                      marker=mk, label=st if st != "own" else "HET-A")
    ax[0].set(xlabel="cores / die area (%)", ylabel="hottest core at nominal power (°C)",
              title="denser chips run hotter")
    ax[0].legend()
    lim = [60, 82]
    ax[1].plot(lim, lim, "k:", lw=0.8)
    ax[1].set(xlabel="mean big-core temperature (°C)", ylabel="mean little-core temperature (°C)",
              title="little cores are hotter (nominal power)", xlim=lim, ylim=lim)
    fig.savefig(OUT / "peak_vs_density.png")

    # (b) example generated power: a phase trace and random steady vectors
    fp = F.get("s4_fp001")
    P = powergen.phase_trace(fp, 5000, seed=11)
    fig, ax = plt.subplots(figsize=(8, 3))
    for j in range(fp.n_power):
        ax.plot(np.arange(5000) * 1e-3, P[:, j] + 0.15 * j,
                label=f"{fp.power_names[j]} ({fp.power_types[j]})", lw=0.8)
    ax.set(xlabel="time (s)", ylabel="power (W, offset per core)",
           title="generated phase trace, s4_fp001 (seed 11)")
    ax.legend(fontsize=6, ncol=4)
    fig.savefig(OUT / "phase_trace_example.png")
    Ps = powergen.random_steady(fp, 1000, seed=1)
    lo, hi = fp.power_bounds()
    save_json(OUT / "summary.json", dict(
        n_floorplans=len(fps),
        nominal_peak_range_C=[min(r["nominal_peak_core_C"] for r in rows[:23]),
                              max(r["nominal_peak_core_C"] for r in rows[:23])],
        max_peak_range_C=[min(r["max_peak_core_C"] for r in rows[:23]),
                          max(r["max_peak_core_C"] for r in rows[:23])],
        random_steady_within_bounds=bool(((Ps >= lo) & (Ps <= hi)).all())))


if __name__ == "__main__":
    main()
