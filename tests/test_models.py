"""Tests for the predictor models on a synthetic linear thermal system (no HotSpot needed).

Run:  python3 -m pytest tests/      (or  python3 tests/test_models.py)
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.ltp.models import SteadyG, SumExp, ARX, FirstOrderLag, CompressedG  # noqa: E402
from src.ltp.predictor import Predictor  # noqa: E402

AMB = 318.15
rng = np.random.default_rng(0)
N_OUT, N_IN, TAU = 5, 3, np.array([0.004, 0.08, 1.5])
A_TRUE = rng.uniform(0.05, 0.6, (N_OUT, N_IN, len(TAU)))


def true_step(t):
    return np.einsum("tm,ijm->tij", 1 - np.exp(-t[:, None] / TAU[None]), A_TRUE)


def simulate(P, dt):
    return SumExp(A_TRUE, TAU, AMB).transient(P, dt)


def test_steady_exact():
    G = A_TRUE.sum(2)
    m = SteadyG.calibrate([G[:, j] for j in range(N_IN)], AMB)
    P = rng.uniform(0, 10, (20, N_IN))
    assert np.allclose(m.steady(P), AMB + P @ G.T)
    assert np.allclose(m.steady(P[0]), AMB + G @ P[0])


def test_sumexp_recovers_time_constants():
    t = np.logspace(-3, 1.5, 120)
    m = SumExp.calibrate(A_TRUE.sum(2), t, true_step(t), 3, AMB)
    assert np.allclose(np.sort(m.tau), TAU, rtol=1e-3)
    assert np.abs(m.step_response(t) - true_step(t)).max() < 1e-6


def test_sumexp_transient_matches_step_response():
    dt, K = 1e-3, 400
    m = SumExp(A_TRUE, TAU, AMB)
    P = np.zeros((K, N_IN)); P[:, 1] = 1.0
    T = m.transient(P, dt) - AMB
    assert np.allclose(T, true_step(dt * np.arange(1, K + 1))[:, :, 1])


def test_arx_fits_linear_system():
    dt = 1e-3
    P = np.repeat(rng.uniform(0, 5, (600, N_IN)), 10, axis=0)
    T = simulate(P, dt)
    m = ARX.calibrate(A_TRUE.sum(2), P, T, AMB, na=3, nb=3)
    P2 = np.repeat(rng.uniform(0, 5, (100, N_IN)), 20, axis=0)
    assert np.abs(m.transient(P2) - simulate(P2, dt)).max() < 0.05


def test_first_order_lag_converges_to_G():
    G = A_TRUE.sum(2)
    t = np.logspace(-3, 1.5, 80)
    S = [true_step(t)[:, :, j] for j in range(N_IN)]
    m = FirstOrderLag.calibrate(G, t, S, AMB)
    P = np.ones((20000, N_IN))
    assert np.allclose(m.transient(P, 1e-3)[-1], AMB + G @ P[0], atol=1e-3)


def test_compressed_g_full_k_is_exact():
    G = A_TRUE.sum(2)
    c_in, c_out = rng.uniform(0, 1, (N_IN, 2)), rng.uniform(0, 1, (N_OUT, 2))
    m = CompressedG.calibrate(G, c_in, c_out, N_IN - 1, AMB)
    assert np.allclose(m.G, G)
    P = rng.uniform(0, 3, (7, N_IN))
    assert np.allclose(m.steady(P), AMB + P @ G.T)


def test_predictor_roundtrip_and_forecast(tmp_path=Path("/tmp")):
    G = A_TRUE.sum(2)
    p = Predictor([f"b{i}" for i in range(N_OUT)], [f"p{j}" for j in range(N_IN)], AMB, G,
                  A_TRUE, TAU)
    f = Path(tmp_path) / "ltp_test_model.npz"
    p.save(f)
    q = Predictor.load(f)
    P = rng.uniform(0, 4, (300, N_IN))
    assert np.allclose(q.transient(P, 1e-3), simulate(P, 1e-3))
    # forecast anchored on the true temperature equals the true future for an exact model
    z = q.run_state(P[:200], 1e-3)
    T_true = simulate(P, 1e-3)
    fc = q.forecast(T_true[199], z, P[200:], 1e-3)
    assert np.allclose(fc, T_true[200:])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
