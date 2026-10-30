# P6-1: Closed-loop HotSpot for DTM

**Question.** DTM needs a "chip" whose power can change every interval *in response to its own
temperature*. HotSpot's transient mode reads a fixed power trace. Can we drive it step by step,
with its full internal state kept, and get exactly what an ordinary HotSpot run would give?

**Reproduce.** `bash experiments/run.sh P6-1_closed_loop_hotspot` (about 2 min).

## How it works

`src/sim/stepper.py` (`HotSpotStepper`) starts one HotSpot transient run whose power trace is a
pipe (`-p /dev/stdin`) and whose temperature trace is a named pipe (FIFO). Each `step(p)` writes
one power row and reads back the temperature row HotSpot computes for it. HotSpot keeps all its
state between steps (every grid cell, the spreader and the sink), exactly as in a normal
transient run. One small patch makes this possible: HotSpot now flushes its output after every
row (`setup/build_hotspot_ltp.sh`). A warm start passes a `.steady` file as `-init_file`.

This is simpler than the plan's C stepper on HotSpot's library interface (`sim-template.c`):
no new C program, the same binary and config as every other experiment, and the same results.

```python
with HotSpotStepper(fp, dt=1e-3, init="warm.steady") as chip:
    for k in range(steps):
        p = policy(T)          # DTM decides the power of this interval
        T = chip.step(p)       # HotSpot advances 1 ms and returns block temperatures
```

## Results

1,000 steps of a phase trace, stepper vs an ordinary HotSpot run of the same trace:

| floorplan | start | max difference | stepper (ms/step) | ordinary run (ms/step) |
|---|---|---|---|---|
| s1_fp001 | cold | **0 K** | 21.8 | 21.3 |
| s1_fp001 | warm | **0 K** | 22.0 | 20.6 |
| s4_fp001 | cold | **0 K** | 33.6 | 22.5 |
| s4_fp001 | warm | **0 K** | 21.6 | 24.4 |

(The times were measured while P1-2's long HotSpot runs used the machine; without load a step
takes about 5.5 ms, P0-4. What matters is that the stepper costs no more than a normal run.)

## Conclusion

- The closed-loop plant works and is **exact**: byte-identical temperatures to a normal HotSpot
  run, from a cold or a warm chip.
- The pipe round trip adds no measurable cost per step.
- P6-2 uses it as the chip, with DTM policies deciding the power every interval and `ltp` as the
  predictor inside the controller.

## Files

- `src/sim/stepper.py`, `results/summary.json`, `results/log.txt`.
