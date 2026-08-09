"""
k0_backend.py — NIR LIF → K0 normative arithmetic compiler/simulator
======================================================================
Compiles a NIR graph containing LIF neurons into a K0-deterministic
simulation. All arithmetic is performed using K0-Full operations
(k0_mul_normative / k0_add_sat) — zero float in the hot path.

K0 fixed-point convention: Q32.32 (32 integer bits, 32 fractional bits).
  Real value r ≈ x / 2**32, where x is a signed 64-bit integer.

Usage
-----
    import nir
    import numpy as np
    from nir_k0.k0_backend import K0Backend, k0_from_nir

    # Build a tiny NIR graph
    graph = nir.NIRGraph(
        nodes={"lif0": nir.LIF(tau=np.array([20e-3]), r=np.array([1.0]),
                               v_threshold=np.array([1.0]), v_leak=np.array([0.0]))},
        edges=[],
    )
    backend = k0_from_nir(graph)
    backend.reset()
    for step in range(100):
        spikes = backend.step({"lif0": [10_000_000]})   # Q32.32 input
    # Determinism check:
    h1 = backend.transcript_hash()
    backend.reset()
    for step in range(100):
        backend.step({"lif0": [10_000_000]})
    h2 = backend.transcript_hash()
    assert h1 == h2, "S2 FAIL"

K0 Arithmetic (pure Python, mirrors ax.c exactly)
-------------------------------------------------
These functions match the C reference:  ax_add_sat / ax_mul_normative.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Dict, List, Optional

import nir
import numpy as np

# ---------------------------------------------------------------------------
# K0 arithmetic constants
# ---------------------------------------------------------------------------
I64_MAX = (1 << 63) - 1
I64_MIN = -(1 << 63)
U128_MASK = (1 << 128) - 1
_FRAC = 32          # fractional bits in Q32.32

# Sentinel flags (returned alongside result, like C's AX_SATURATED / AX_TRUNCATED)
AX_OK         = 0x00
AX_SATURATED  = 0x01
AX_TRUNCATED  = 0x02


def _clamp_i64(x: int) -> int:
    if x > I64_MAX:
        return I64_MAX
    if x < I64_MIN:
        return I64_MIN
    return x


def k0_add_sat(a: int, b: int) -> tuple[int, int]:
    """Saturating add matching ax_add_sat(). Returns (result, flags)."""
    p = a + b          # Python int: arbitrary precision
    flag = AX_OK
    if p > I64_MAX or p < I64_MIN:
        p = _clamp_i64(p)
        flag = AX_SATURATED
    return p, flag


def k0_mul_normative(a: int, b: int) -> tuple[int, int]:
    """
    Q32.32 × Q32.32 → Q32.32 normative multiply matching ax_mul_normative().
    GRS round-to-nearest-even applied to bits [31:0] of the 128-bit product.
    Returns (result, flags).
    """
    # 128-bit product (signed × signed via Python big int)
    p128 = a * b  # may be negative (Python handles sign correctly)

    # Interpret as unsigned for bit manipulation
    if p128 < 0:
        p128_u = p128 & U128_MASK
    else:
        p128_u = p128

    # Q >> 32: arithmetic right shift (integer quotient in Q32.32)
    # Q is bits [127:32] of p128 as a signed 64-bit value
    q_full = p128 >> _FRAC   # Python arithmetic right shift
    # low 32 bits are bits [31:0] of unsigned p128
    low = int(p128_u & 0xFFFFFFFF)

    # GRS bits from low 32 bits
    g = (low >> 31) & 1
    r = (low >> 30) & 1
    s = 1 if (low & 0x3FFFFFFF) != 0 else 0

    # Round-to-nearest-even
    if g and (r or s or (q_full & 1)):
        q_full += 1

    flags = AX_TRUNCATED if (low != 0) else AX_OK
    result = _clamp_i64(q_full)
    if result != q_full:
        flags |= AX_SATURATED
    return result, flags


def float_to_q3232(x: float) -> int:
    """Convert a Python float to Q32.32 integer."""
    return _clamp_i64(int(round(x * (1 << _FRAC))))


def q3232_to_float(x: int) -> float:
    """Convert Q32.32 integer to Python float (for display only, NOT used in hot path)."""
    return x / (1 << _FRAC)


# ---------------------------------------------------------------------------
# Serialisation helpers (match ax.c little-endian transcript)
# ---------------------------------------------------------------------------

def _serialize_i64_le(v: int) -> bytes:
    v &= (1 << 64) - 1          # to unsigned 64-bit
    return struct.pack("<Q", v)


def _serialize_u32_le(v: int) -> bytes:
    return struct.pack("<I", v & 0xFFFFFFFF)


# ---------------------------------------------------------------------------
# K0 LIF neuron state
# ---------------------------------------------------------------------------

class K0LIFNeuron:
    """
    Single K0-deterministic LIF neuron.
    All state stored as Q32.32 integers.

    Parameters derived from NIR LIF node:
      tau_q    : membrane time constant (Q32.32)
      r_q      : resistance (Q32.32)
      vthr_q   : spike threshold (Q32.32)
      vleak_q  : leak (resting) potential (Q32.32)
    """

    __slots__ = ("tau_q", "r_q", "vthr_q", "vleak_q", "v_q", "status")

    def __init__(
        self,
        tau_q: int,
        r_q: int,
        vthr_q: int,
        vleak_q: int,
    ) -> None:
        self.tau_q   = tau_q
        self.r_q     = r_q
        self.vthr_q  = vthr_q
        self.vleak_q = vleak_q
        self.v_q: int = vleak_q   # membrane potential
        self.status: int = AX_OK

    def reset(self) -> None:
        self.v_q = self.vleak_q
        self.status = AX_OK

    def step(self, i_q: int, dt_q: int) -> int:
        """
        One timestep. Returns 1 if spike, else 0.
        Discrete Euler: v += dt/tau * (v_leak - v + r*I)
        All in Q32.32 integer arithmetic.
        """
        # decay = dt_q / tau_q  (Q32.32 / Q32.32 → Q32.32 via mul of reciprocal)
        # We pre-compute 1/tau as tau_inv_q = round(2^32 / tau_float)
        # But to stay integer-only, we do: decay_num = dt_q; decay_den = tau_q
        # Approximation: decay = dt_q * (1<<32) // tau_q (integer division → Q32.32)
        # This matches the normative approach: multiply then shift.

        # r*I (Q32.32)
        rI, fl = k0_mul_normative(self.r_q, i_q)
        self.status |= fl

        # v_leak - v
        diff_leak, fl = k0_add_sat(self.vleak_q, -self.v_q)
        self.status |= fl

        # (v_leak - v + r*I)
        drive, fl = k0_add_sat(diff_leak, rI)
        self.status |= fl

        # dt/tau * drive
        # dt/tau = dt_q * (2^32 / tau_q) >> 32  — use normative mul
        # We encode dt/tau directly as dt_q if tau_q == 1<<32 (tau=1 s) for generality.
        # General case: dt_over_tau_q = dt_q * ONE_Q / tau_q
        # We use integer division to get the Q32.32 ratio:
        if self.tau_q != 0:
            ONE_Q32 = 1 << _FRAC
            dt_over_tau_q = (dt_q * ONE_Q32) // self.tau_q   # integer division
            dt_over_tau_q = _clamp_i64(dt_over_tau_q)
        else:
            dt_over_tau_q = float_to_q3232(1.0)

        dv, fl = k0_mul_normative(dt_over_tau_q, drive)
        self.status |= fl

        self.v_q, fl = k0_add_sat(self.v_q, dv)
        self.status |= fl

        # Spike check
        if self.v_q >= self.vthr_q:
            self.v_q = self.vleak_q   # reset
            return 1
        return 0


# ---------------------------------------------------------------------------
# K0 Network (compiled from NIR graph)
# ---------------------------------------------------------------------------

class K0Backend:
    """
    K0-deterministic backend compiled from a NIR graph.
    Only nir.LIF nodes are supported (others raise NotImplementedError).

    transcript: list of (node_id, step, spike, v_q) — used for S2 hash.
    """

    def __init__(
        self,
        neurons: Dict[str, List[K0LIFNeuron]],
        dt: float = 1e-3,
    ) -> None:
        self.neurons = neurons
        self.dt_q = float_to_q3232(dt)
        self._step: int = 0
        self._transcript: List[bytes] = []

    # ------------------------------------------------------------------
    def reset(self) -> None:
        for pop in self.neurons.values():
            for n in pop:
                n.reset()
        self._step = 0
        self._transcript = []

    # ------------------------------------------------------------------
    def step(self, inputs: Dict[str, List[int]]) -> Dict[str, List[int]]:
        """
        One timestep.
        inputs: {node_id: [i_q_0, i_q_1, ...]} in Q32.32
        Returns spikes: {node_id: [0/1, ...]}.
        """
        spikes: Dict[str, List[int]] = {}
        for node_id, pop in self.neurons.items():
            in_list = inputs.get(node_id, [0] * len(pop))
            sp_list: List[int] = []
            for j, (neuron, i_q) in enumerate(zip(pop, in_list)):
                sp = neuron.step(i_q, self.dt_q)
                sp_list.append(sp)
                # Append to transcript (little-endian, same pattern as ax.c)
                self._transcript.append(_serialize_i64_le(neuron.v_q))
                self._transcript.append(_serialize_u32_le(sp))
            spikes[node_id] = sp_list
        self._step += 1
        return spikes

    # ------------------------------------------------------------------
    def transcript_hash(self) -> str:
        """SHA-256 of the full transcript — determinism certificate."""
        h = hashlib.sha256()
        for chunk in self._transcript:
            h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    def membrane_voltages(self) -> Dict[str, List[float]]:
        """Return current membrane voltages as floats (for display/debug only)."""
        return {
            nid: [q3232_to_float(n.v_q) for n in pop]
            for nid, pop in self.neurons.items()
        }


# ---------------------------------------------------------------------------
# NIR → K0 compiler
# ---------------------------------------------------------------------------

def k0_from_nir(graph: nir.NIRGraph, dt: float = 1e-3) -> K0Backend:
    """
    Compile a NIR graph to a K0Backend.
    Currently supports: nir.LIF, nir.Input (ignored), nir.Output (ignored).
    Raises NotImplementedError for unsupported node types.
    """
    neurons: Dict[str, List[K0LIFNeuron]] = {}

    for node_id, node in graph.nodes.items():
        if isinstance(node, nir.LIF):
            # NIR LIF parameters are arrays (one per neuron in the population)
            tau_arr    = np.atleast_1d(np.asarray(node.tau,         dtype=float))
            r_arr      = np.atleast_1d(np.asarray(node.r,           dtype=float))
            vthr_arr   = np.atleast_1d(np.asarray(node.v_threshold, dtype=float))
            vleak_arr  = np.atleast_1d(np.asarray(node.v_leak,      dtype=float))

            n_neurons = len(tau_arr)
            pop: List[K0LIFNeuron] = []
            for i in range(n_neurons):
                pop.append(K0LIFNeuron(
                    tau_q   = float_to_q3232(float(tau_arr[i])),
                    r_q     = float_to_q3232(float(r_arr[i])),
                    vthr_q  = float_to_q3232(float(vthr_arr[i])),
                    vleak_q = float_to_q3232(float(vleak_arr[i])),
                ))
            neurons[node_id] = pop

        elif isinstance(node, (nir.Input, nir.Output)):
            pass  # structural nodes — no computation

        elif isinstance(node, nir.Affine):
            # Affine (linear) layers not yet in hot path — raise with guidance
            raise NotImplementedError(
                f"Node '{node_id}' is nir.Affine — not yet supported. "
                "Flatten the graph to LIF-only before compiling to K0."
            )
        else:
            raise NotImplementedError(
                f"Node '{node_id}' has unsupported type {type(node).__name__}. "
                "K0 backend supports: LIF, Input, Output."
            )

    return K0Backend(neurons=neurons, dt=dt)
