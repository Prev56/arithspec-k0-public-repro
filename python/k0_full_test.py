"""
k0_full_test.py — Port Python K0-Full (INT64 Q32.32)
Test de conformance : doit produire le même SHA-256 que la version C (ax_k0_test.c)

USAGE :
  python k0_full_test.py
  # → AX_K0_TEST_SHA256=<hash>

Ce script est la référence Python pour la cellule (Python, variante Full) de la
matrice de conformance 3×3.
"""
from __future__ import annotations

import hashlib
import struct

# ─── Arithmétique K0-Full (INT64 Q32.32) ──────────────────────────────────────

INT64_MAX = (1 << 63) - 1
INT64_MIN = -(1 << 63)


def clamp64(x: int) -> int:
    if x > INT64_MAX:
        return INT64_MAX
    if x < INT64_MIN:
        return INT64_MIN
    return x


def ax_add_sat(a: int, b: int) -> tuple:
    """ADD_SAT K0-Full. Retourne (résultat, saturated: bool)."""
    s = a + b
    if s > INT64_MAX:
        return INT64_MAX, True
    if s < INT64_MIN:
        return INT64_MIN, True
    return s, False


def ax_mul_normative(a: int, b: int) -> tuple:
    """MUL_NORMATIVE K0-Full avec GRS+RNE, conforme spec §4.2.
    Retourne (résultat, truncated: bool, saturated: bool).
    - truncated : information perdue (low != 0)
    - saturated : résultat arrondi hors plage int64 (clampage appliqué)
    Utilise les entiers Python illimités comme équivalent de __int128.
    """
    # Produit exact Q64.64
    product = a * b   # Python int illimité = équivalent __int128
    # Candidat Q32.32 (décalage de 32 bits)
    q, rem = divmod(product, (1 << 32))
    # rem est un uint32 logique (32 bits de garde)
    rem_u32 = rem & 0xFFFFFFFF

    # Bits GRS extraits
    G = (rem_u32 >> 31) & 1
    R = (rem_u32 >> 30) & 1
    S = 1 if (rem_u32 & 0x3FFFFFFF) != 0 else 0

    # Arrondi RNE (ties-to-even)
    if G == 1 and (R == 1 or S == 1 or (q & 1) == 1):
        q += 1

    truncated = rem_u32 != 0

    clamped = clamp64(q)
    saturated = (clamped != q)   # saturation si q hors plage int64

    return clamped, truncated, saturated


def ax_emit_o1(x: int, theta: int, emit_cap: int) -> tuple:
    """EMIT_O1 K0-Full. Retourne (x_new, emit, flags: dict)."""
    flags = {"div_zero": False, "input_range": False, "burst_crop": False,
             "saturated": False, "truncated": False}
    if theta <= 0:
        flags["div_zero"] = True
        return x, 0, flags
    if x < 0:
        flags["input_range"] = True
        return x, 0, flags

    # Nombre d'impulsions (division entière tronquée, x et theta positifs)
    emit = x // theta

    if emit > emit_cap:
        emit = emit_cap
        flags["burst_crop"] = True

    # Drain : emit * theta (en Q32.32)
    # emit est un entier, on le représente en Q32.32 : emit_q = emit << 32
    emit_q = emit << 32
    drain, trunc, sat_mul = ax_mul_normative(emit_q, theta)
    if trunc:
        flags["truncated"] = True
    if sat_mul:
        flags["saturated"] = True
    x_new, sat_add = ax_add_sat(x, -drain)
    if sat_add:
        flags["saturated"] = True

    return x_new, emit, flags


# ─── PRNG splitmix64 ──────────────────────────────────────────────────────────

def splitmix64(state: list) -> int:
    """splitmix64 — retourne uint64."""
    z = (state[0] + 0x9e3779b97f4a7c15) & 0xFFFFFFFFFFFFFFFF
    state[0] = z
    z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & 0xFFFFFFFFFFFFFFFF
    return z ^ (z >> 31)


def to_int64(x: int) -> int:
    """Convertit un uint64 en int64 signé."""
    x &= 0xFFFFFFFFFFFFFFFF
    if x >= (1 << 63):
        return x - (1 << 64)
    return x


# ─── Suite de test normative (identique à ax_k0_test.c) ──────────────────────

def run_k0_full_test(n: int = 200_000) -> str:
    """Exécute la suite de test normative K0-Full sur N=200k itérations.
    Retourne le hash SHA-256 de la trajectoire.
    
    IMPORTANT : doit être bit-exact avec la version C (ax_k0_test.c).
    Sérialisation little-endian identique à feed_u64 / feed_u32 en C.
    """
    seed = 0xA10 + 0x123456789abcdef0  # = 0x123456789abce000 — seed normative
    state = [seed & 0xFFFFFFFFFFFFFFFF]

    h = hashlib.sha256()

    def feed_i64(v: int) -> None:
        """Sérialise int64 en little-endian (identique feed_u64 en C pour unsigned)."""
        # Python struct "<q" = int64 LE
        h.update(struct.pack("<q", v))

    def feed_u32(v: int) -> None:
        h.update(struct.pack("<I", v & 0xFFFFFFFF))

    for _ in range(n):
        # Générer les paramètres (identique à ax_k0_test.c)
        a_raw = splitmix64(state)
        b_raw = splitmix64(state)
        x_raw = splitmix64(state)
        t_raw = splitmix64(state)
        c_raw = splitmix64(state)

        # Convertir en int64 signés — IDENTIQUE au C (as_scalar = cast direct)
        # theta: forcé impair (| 1) mais PAS forcé positif — peut être négatif
        # x: brut signé — ax_emit_o1 gère le cas x<0 (AX_INPUT_RANGE)
        a = to_int64(a_raw)
        b = to_int64(b_raw)
        x = to_int64(x_raw)
        theta = to_int64(t_raw | 1)   # impair, signé (peut être négatif → AX_DIV_ZERO)
        cap = (c_raw % 128) + 1

        # Opérations normatives
        r_add, sat_add = ax_add_sat(a, b)
        r_mul, trunc_mul, sat_mul = ax_mul_normative(a, b)
        x2, emit, flags = ax_emit_o1(x, theta, cap)

        # Status cumulatif (identique au C — st accumule tout)
        # ax_add_sat(a,b,&st) → AX_SATURATED
        # ax_mul_normative(a,b,&st) → AX_TRUNCATED + AX_SATURATED si overflow
        # ax_emit_o1(x,theta,cap,&emit,&st) → AX_DIV_ZERO|AX_INPUT_RANGE|AX_BURST_CROP|AX_SATURATED|AX_TRUNCATED
        st = 0
        if sat_add:              st |= (1 << 0)   # AX_SATURATED depuis add_sat(a,b)
        if sat_mul:              st |= (1 << 0)   # AX_SATURATED depuis mul_normative(a,b)
        if trunc_mul:            st |= (1 << 1)   # AX_TRUNCATED depuis mul_normative(a,b)
        if flags["burst_crop"]:  st |= (1 << 2)
        if flags["input_range"]: st |= (1 << 3)
        if flags["div_zero"]:    st |= (1 << 4)
        if flags["saturated"]:   st |= (1 << 0)   # AX_SATURATED depuis emit_o1
        if flags["truncated"]:   st |= (1 << 1)   # AX_TRUNCATED depuis emit_o1

        # Ingestion dans SHA-256 (ordre identique à ax_k0_test.c)
        feed_i64(r_add)
        feed_i64(r_mul)
        feed_i64(x2)
        feed_i64(emit)
        feed_u32(st)

    return h.hexdigest()


if __name__ == "__main__":
    import time
    print("K0-Full Python conformance test — N=200 000")
    t0 = time.perf_counter()
    h = run_k0_full_test(200_000)
    elapsed = time.perf_counter() - t0
    print(f"AX_K0_TEST_SHA256={h}")
    print(f"Durée: {elapsed:.2f}s")
    print()
    print("NOTE: Ce hash doit être identique à la sortie de ./k0_test (C)")
    print("      Une fois le hash de référence C établi, mettre à jour CONFORMANCE.md §7")
