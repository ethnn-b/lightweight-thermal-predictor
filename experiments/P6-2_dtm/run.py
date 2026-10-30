"""P6-2 [WISH]: reactive vs proactive DTM, with HotSpot as the chip in the loop.

Plant: HotSpot grid 64x64 driven step by step (src/sim/stepper.py, P6-1), Δt = 1 ms, warm start
at the steady state of the workload's average power. Sensors: core block temperatures.
Workload: every core requests power from a phase trace within the TA ranges (big 10-20 W, little
5-10 W; requests change every 1 ms to 2 s). Actuator: per-core DVFS level f in
{1.0, 0.9, ..., 0.5}; delivered power = request * (0.2 + 0.8 f^3) (20 % static); work done = f.
A DTM decision every 10 ms. Temperature limit per floorplan: midway between its hottest core at
TA nominal power and at max power (P0-5).
Policies:
  none                    f = 1 always
  reactive                a core over the limit drops one level; below limit - 1 K it climbs one
  proactive (T3 / T1 / persistence predictor)
                          every 10 ms, forecast the next 20 ms for candidate levels (assuming each
                          core's request stays as it is now) and pick the highest levels whose
                          forecast stays below limit - 0.2 K; greedy: start one level up, lower
                          the worst core until no forecast violation.
Metrics: peak temperature, core-ms above the limit, violation episodes, throughput (mean f),
predictor time per decision.
"""
import time

import numpy as np

from common import results_dir, save_csv, save_json, md_table, plt
from src.sim import floorplans as F, hotspot as H, powergen
from src.sim.parallel import pmap
from src.sim.stepper import HotSpotStepper
from src.ltp import calibrate as C
from src.ltp.models import SumExp, FirstOrderLag

OUT = results_dir(__file__)
DT, STEPS, PERIOD, HORIZON = 1e-3, 4000, 10, 20
LEVELS = np.array([1.0, 0.9, 0.8, 0.7, 0.6, 0.5])
LIMITS_C = {"s1_fp001": (76.4 + 82.9) / 2, "s4_fp001": (69.3 + 73.9) / 2}
TIGHTER = 3.0      # second scenario: limit 3 K lower, so DTM has to throttle a lot
MARGIN = 0.2


def power(req, lv):
    f = LEVELS[lv]
    return req * (0.2 + 0.8 * f ** 3)


class T3Forecaster:
    def __init__(self, m, core):
        self.m, self.core = m, core
        self.lam = np.exp(-DT / m.tau)
        self.Af = m.A.reshape(m.A.shape[0], -1)[core]
        self.z = None
        k = np.arange(1, HORIZON + 1)[:, None]
        self.lk = self.lam[None, :] ** k                       # (H, M)

    def reset(self, p0):
        self.z = np.repeat(p0[:, None], len(self.m.tau), 1)

    def update(self, p):
        self.z = self.lam * self.z + (1 - self.lam) * p[:, None]

    def forecast(self, T_now, p):
        """Core temperatures for the next HORIZON steps at constant power p, anchored on T_now."""
        zk = self.lk[:, None, :] * self.z[None] + (1 - self.lk[:, None, :]) * p[None, :, None]
        T = self.m.t_amb + zk.reshape(HORIZON, -1) @ self.Af.T
        now = self.m.t_amb + self.Af @ self.z.ravel()
        return T + (T_now - now)


class T1Forecaster:
    def __init__(self, m, core):
        self.G, self.tau, self.amb = m.G[core], m.tau[core], m.t_amb
        k = np.arange(1, HORIZON + 1)[:, None]
        self.ak = np.exp(-DT / self.tau)[None, :] ** k

    def reset(self, p0):
        pass

    def update(self, p):
        pass

    def forecast(self, T_now, p):
        x0, target = T_now - self.amb, self.G @ p
        return self.amb + self.ak * x0 + (1 - self.ak) * target


class Persistence:
    def reset(self, p0):
        pass

    def update(self, p):
        pass

    def forecast(self, T_now, p):
        return np.tile(T_now, (HORIZON, 1))


def run_policy(fp_name, policy, tight=False, M=4):
    fp = F.get(fp_name)
    core = fp.power_idx
    N = fp.n_power
    req = powergen.phase_trace(fp, STEPS, seed=31, levels=4, max_phase=2000)
    req = np.maximum(req, fp.power_bounds()[0] + 0.5 * (fp.power_bounds()[1] - fp.power_bounds()[0]))
    limit_C = LIMITS_C[fp_name] - (TIGHTER if tight else 0.0)
    limit = limit_C + 273.15
    cal = C.run_calibration_runs(fp)
    t, Y = C.merged_samples(cal)
    fc = None
    if policy.startswith("proactive"):
        kind = policy.split("(")[1].rstrip(")")
        if kind == "T3":
            fc = T3Forecaster(SumExp.calibrate(cal["G"], t, Y, M, H.AMBIENT), core)
        elif kind == "T1":
            fc = T1Forecaster(FirstOrderLag.calibrate(cal["G"], t, [Y[:, :, j] for j in range(N)],
                                                      H.AMBIENT), core)
        else:
            fc = Persistence()
    p_avg = req.mean(0)
    st = H.steady(fp, p_avg, group="P6-2")
    lv = np.zeros(N, int)
    T_now = st["T"][core]
    if fc:
        fc.reset(p_avg)
    temps, levels, dec_times = [], [], []
    with HotSpotStepper(fp, DT, init=f"{st['dir']}/out.steady") as chip:
        for k in range(STEPS):
            if k % PERIOD == 0:
                if policy == "reactive":
                    lv = np.where(T_now > limit, np.minimum(lv + 1, len(LEVELS) - 1),
                                  np.where(T_now < limit - 1.0, np.maximum(lv - 1, 0), lv))
                elif fc is not None:
                    t0 = time.perf_counter()
                    cand = np.maximum(lv - 1, 0)
                    for _ in range(N * len(LEVELS)):
                        Tf = fc.forecast(T_now, power(req[k], cand)).max(0)
                        over = Tf - (limit - MARGIN)
                        bad = np.where((over > 0) & (cand < len(LEVELS) - 1))[0]
                        if len(bad) == 0:
                            break
                        cand[bad[np.argmax(over[bad])]] += 1
                    lv = cand
                    dec_times.append(time.perf_counter() - t0)
            p = power(req[k], lv)
            T = chip.step(p)
            if fc:
                fc.update(p)
            T_now = T[core]
            temps.append(T_now)
            levels.append(LEVELS[lv])
    temps, levels = np.array(temps), np.array(levels)
    over = temps > limit
    any_over = over.any(1)
    episodes = int(np.sum(any_over[1:] & ~any_over[:-1]) + any_over[0])
    return dict(floorplan=fp_name, scenario="tight" if tight else "normal", policy=policy,
                limit_C=limit_C,
                peak_C=float(temps.max() - 273.15),
                core_ms_over_limit=float(over.sum() * DT * 1e3),
                ms_any_core_over=float(any_over.sum() * DT * 1e3),
                episodes=episodes, throughput=float(levels.mean()),
                decision_us=float(np.median(dec_times) * 1e6) if dec_times else 0.0,
                _temps=temps, _levels=levels)


def main():
    policies = ["none", "reactive", "proactive (T3)", "proactive (T1)", "proactive (persistence)"]
    jobs = [dict(fp_name=n, policy=p, tight=t) for t in (False, True) for n in LIMITS_C
            for p in policies]
    res = pmap(run_policy, jobs)
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in res]
    save_csv(OUT / "results.csv", rows)
    print(md_table(rows, "{:.3g}"))
    save_json(OUT / "summary.json", rows)

    for n in LIMITS_C:
      for scen in ("normal", "tight"):
        fig, axes = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
        tt = np.arange(1, STEPS + 1) * DT
        lim = None
        for r in res:
            if r["floorplan"] != n or r["scenario"] != scen or r["policy"] == "proactive (persistence)":
                continue
            lim = r["limit_C"]
            axes[0].plot(tt, r["_temps"].max(1) - 273.15, lw=0.8, label=r["policy"])
            axes[1].plot(tt, r["_levels"].mean(1), lw=0.8, label=r["policy"])
        axes[0].axhline(lim, color="k", ls=":", label="limit")
        axes[0].set(ylabel="hottest core (°C)", title=f"DTM on {n}, {scen} limit ({lim:.1f} °C)")
        axes[1].set(xlabel="time (s)", ylabel="mean DVFS level f")
        axes[0].legend(fontsize=7, ncol=3)
        fig.savefig(OUT / f"dtm_{n}_{scen}.png")


if __name__ == "__main__":
    main()
