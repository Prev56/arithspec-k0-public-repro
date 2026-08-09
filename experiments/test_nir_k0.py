"""
test_nir_k0.py — NIR LIF → K0 backend : tests de conformité et déterminisme
============================================================================
Execute: python test_nir_k0.py
"""
import sys, hashlib, json
sys.path.insert(0, r"python")

import nir
import numpy as np
from nir_k0.k0_backend import (
    K0Backend, k0_from_nir,
    k0_add_sat, k0_mul_normative,
    float_to_q3232, q3232_to_float,
    AX_OK, AX_SATURATED, AX_TRUNCATED,
)

REF_K0_HASH = "45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = {}

# ────────────────────────────────────────────────────────────────────────────
# T01 : k0_add_sat — identité et saturation
# ────────────────────────────────────────────────────────────────────────────
def t01_add_sat():
    I64_MAX = (1 << 63) - 1
    I64_MIN = -(1 << 63)
    r, f = k0_add_sat(1 << 32, 1 << 32)
    assert r == (1 << 33) and f == AX_OK, f"T01a fail: r={r} f={f}"
    r, f = k0_add_sat(I64_MAX, 1)
    assert r == I64_MAX and f == AX_SATURATED, f"T01b saturate fail: r={r} f={f}"
    r, f = k0_add_sat(I64_MIN, -1)
    assert r == I64_MIN and f == AX_SATURATED, f"T01c saturate neg fail"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T02 : k0_mul_normative — identité Q32.32
# ────────────────────────────────────────────────────────────────────────────
def t02_mul_normative():
    ONE = 1 << 32  # 1.0 in Q32.32
    r, f = k0_mul_normative(ONE, ONE)
    assert r == ONE and f == AX_OK, f"T02 identity fail: r={r}"
    half = 1 << 31
    r, _ = k0_mul_normative(half, half)
    assert r == (1 << 30), f"T02 half*half fail: r={r}"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T03 : float_to_q3232 / q3232_to_float round-trip
# ────────────────────────────────────────────────────────────────────────────
def t03_qconvert():
    for v in [0.0, 1.0, 0.5, -1.0, 3.14159, 100.0]:
        q = float_to_q3232(v)
        back = q3232_to_float(q)
        err = abs(back - v)
        assert err < 1e-6, f"T03 round-trip fail for {v}: back={back}"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T04 : k0_from_nir — compilation d'un graphe NIR LIF simple
# ────────────────────────────────────────────────────────────────────────────
def t04_nir_compile():
    g = nir.NIRGraph(
        nodes={
            "lif0": nir.LIF(
                tau=np.array([20e-3]),
                r=np.array([1.0]),
                v_threshold=np.array([1.0]),
                v_leak=np.array([0.0]),
            )
        },
        edges=[],
    )
    backend = k0_from_nir(g, dt=1e-3)
    assert "lif0" in backend.neurons, "T04 node missing"
    assert len(backend.neurons["lif0"]) == 1, "T04 wrong pop size"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T05 : S2 — double run → même hash (déterminisme)
# ────────────────────────────────────────────────────────────────────────────
def t05_s2_determinism():
    g = nir.NIRGraph(
        nodes={
            "lif": nir.LIF(
                tau=np.array([10e-3, 20e-3]),
                r=np.array([1.0, 1.5]),
                v_threshold=np.array([1.0, 0.8]),
                v_leak=np.array([0.0, 0.0]),
            )
        },
        edges=[],
    )
    backend = k0_from_nir(g, dt=1e-3)

    inputs = [
        [float_to_q3232(0.1 * i), float_to_q3232(0.07 * i)]
        for i in range(200)
    ]

    def run_and_hash():
        backend.reset()
        for inp in inputs:
            backend.step({"lif": inp})
        return backend.transcript_hash()

    h1 = run_and_hash()
    h2 = run_and_hash()
    assert h1 == h2, f"T05 S2 FAIL: {h1} != {h2}"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T06 : neuron fires when potential exceeds threshold
# Key: steady-state v* = r*I; for spikes, need r*I > v_threshold
# ────────────────────────────────────────────────────────────────────────────
def t06_spike_threshold():
    g = nir.NIRGraph(
        nodes={
            "n": nir.LIF(
                tau=np.array([10e-3]),
                r=np.array([1.0]),
                v_threshold=np.array([0.5]),
                v_leak=np.array([0.0]),
            )
        },
        edges=[],
    )
    backend = k0_from_nir(g, dt=1e-3)
    backend.reset()
    spikes_total = 0
    for _ in range(500):
        inp = [float_to_q3232(1.5)]   # r*I=1.5 >> v_threshold=0.5 → guaranteed spikes
        sp = backend.step({"n": inp})
        spikes_total += sp["n"][0]
    assert spikes_total > 0, "T06 no spikes produced"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T07 : multi-neuron population — lower threshold → more spikes
# Use uniform large input (r*I >> max_threshold) for all neurons.
# ────────────────────────────────────────────────────────────────────────────
def t07_multi_neuron():
    N = 8
    thresholds = np.linspace(0.2, 1.5, N)
    g = nir.NIRGraph(
        nodes={
            "pop": nir.LIF(
                tau=np.ones(N) * 5e-3,
                r=np.ones(N),
                v_threshold=thresholds,
                v_leak=np.zeros(N),
            )
        },
        edges=[],
    )
    backend = k0_from_nir(g, dt=1e-3)
    backend.reset()
    spike_counts = [0] * N
    # Use uniform large input: r*I=3.0 >> max threshold=1.5 → all neurons fire
    inp = [float_to_q3232(3.0)] * N
    for _ in range(2000):
        sp = backend.step({"pop": inp})
        for i, s in enumerate(sp["pop"]):
            spike_counts[i] += s
    # Lower threshold → shorter cycle → more spikes
    assert spike_counts[0] > spike_counts[-1], f"T07 threshold ordering fail: {spike_counts}"
    return True

# ────────────────────────────────────────────────────────────────────────────
# T08 : edges-only graph (no Input/Output nodes) — k0_from_nir skips edges
# Tests that multiple LIF populations compile without error
# ────────────────────────────────────────────────────────────────────────────
def t08_input_output_nodes():
    # NIR 1.0.7 Input/Output constructor API is non-standard;
    # test with a pure LIF-only graph to verify edge handling
    g = nir.NIRGraph(
        nodes={
            "lif_a": nir.LIF(
                tau=np.array([10e-3]),
                r=np.array([1.0]),
                v_threshold=np.array([1.0]),
                v_leak=np.array([0.0]),
            ),
            "lif_b": nir.LIF(
                tau=np.array([5e-3]),
                r=np.array([1.0]),
                v_threshold=np.array([0.5]),
                v_leak=np.array([0.0]),
            ),
        },
        edges=[("lif_a", "lif_b")],  # structural edge, not processed in hot path
    )
    backend = k0_from_nir(g)
    assert "lif_a" in backend.neurons and "lif_b" in backend.neurons
    backend.reset()
    backend.step({"lif_a": [float_to_q3232(2.0)], "lif_b": [float_to_q3232(1.0)]})
    return True

# ────────────────────────────────────────────────────────────────────────────
# T09 : membrane_voltages() output (display only, doesn't need float in hot path)
# ────────────────────────────────────────────────────────────────────────────
def t09_membrane_voltages():
    g = nir.NIRGraph(
        nodes={"n": nir.LIF(
            tau=np.array([10e-3]),
            r=np.array([1.0]),
            v_threshold=np.array([2.0]),
            v_leak=np.array([0.0]),
        )},
        edges=[],
    )
    backend = k0_from_nir(g, dt=1e-3)
    backend.reset()
    for _ in range(10):
        backend.step({"n": [float_to_q3232(0.01)]})
    vd = backend.membrane_voltages()
    assert "n" in vd and len(vd["n"]) == 1
    assert isinstance(vd["n"][0], float)
    return True

# ────────────────────────────────────────────────────────────────────────────
# T10 : transcript_hash changes with different inputs
# ────────────────────────────────────────────────────────────────────────────
def t10_hash_sensitivity():
    g = nir.NIRGraph(
        nodes={"n": nir.LIF(
            tau=np.array([10e-3]),
            r=np.array([1.0]),
            v_threshold=np.array([1.0]),
            v_leak=np.array([0.0]),
        )},
        edges=[],
    )
    backend = k0_from_nir(g, dt=1e-3)

    def run(inp_val):
        backend.reset()
        for _ in range(100):
            backend.step({"n": [float_to_q3232(inp_val)]})
        return backend.transcript_hash()

    h_low  = run(0.001)
    h_high = run(0.1)
    assert h_low != h_high, "T10 hash should differ for different inputs"
    return True

# ────────────────────────────────────────────────────────────────────────────
# Run all tests
# ────────────────────────────────────────────────────────────────────────────
tests = [
    ("T01_add_sat",       t01_add_sat),
    ("T02_mul_normative", t02_mul_normative),
    ("T03_qconvert",      t03_qconvert),
    ("T04_nir_compile",   t04_nir_compile),
    ("T05_s2_determinism",t05_s2_determinism),
    ("T06_spike_threshold",t06_spike_threshold),
    ("T07_multi_neuron",  t07_multi_neuron),
    ("T08_input_output",  t08_input_output_nodes),
    ("T09_membrane_v",    t09_membrane_voltages),
    ("T10_hash_sensitivity", t10_hash_sensitivity),
]

print("\n" + "="*60)
print("  NIR-K0 Backend — Test Suite")
print("="*60)

passed = failed = 0
for name, fn in tests:
    try:
        ok = fn()
        status = PASS if ok else FAIL
        if ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        status = FAIL
        failed += 1
        print(f"  [{status}] {name}: {e}")
        continue
    print(f"  [{status}] {name}")

print("="*60)
verdict = "PASS_FORT" if failed == 0 else f"FAIL ({failed} failed)"
print(f"  {passed}/{len(tests)} PASS — Verdict: {verdict}")
print("="*60)

# Save result
out = {
    "module": "nir_k0_backend",
    "test_count": len(tests),
    "passed": passed,
    "failed": failed,
    "verdict": verdict,
}
import pathlib
pathlib.Path(r"experiments/k0_cross_platform/results/nir_k0_test_results.json").write_text(json.dumps(out, indent=2))
print(f"\n  Résultats → nir_k0_test_results.json")
sys.exit(0 if failed == 0 else 1)
