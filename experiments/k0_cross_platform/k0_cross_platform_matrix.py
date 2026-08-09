"""
k0_cross_platform_matrix.py — Expérience 2 : Matrice 3×3 conformance
(C / Python / Rust) × (x86-64 / aarch64 / RP2040)

OBJECTIF : Générer et vérifier la matrice de conformance K0.
Chaque cellule est identifiée par (lang, platform, hash).
Toutes les cellules de la même variante doivent avoir le même hash.

USAGE (exécuter sur chaque plateforme) :
  python k0_cross_platform_matrix.py --lang python [--out results/]
  
  Pour C (après compilation) :
  k0_test (C) produit le hash directement — l'ingérer manuellement
  via --report-c-hash <hash>

  Pour Rust (après cargo build) :
  cargo run --bin k0_conformance -- (ajouté en Phase 2)

MODE AGRÉGATION (une fois tous les résultats collectés) :
  python k0_cross_platform_matrix.py --aggregate results/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import struct
import sys
import time
from pathlib import Path

_OUTDIR = Path(__file__).parent / "results"
_OUTDIR.mkdir(exist_ok=True)

# Hash de référence K0-Full établi en Phase 1
REFERENCE_HASH_K0_FULL = "45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d"


# ─── Arithmétique K0-Full (copie locale pour autonomie du script) ─────────────

INT64_MAX = (1 << 63) - 1
INT64_MIN = -(1 << 63)


def _clamp64(x: int) -> tuple:
    if x > INT64_MAX:
        return INT64_MAX, True
    if x < INT64_MIN:
        return INT64_MIN, True
    return x, False


def _ax_add_sat(a: int, b: int) -> tuple:
    s = a + b
    c, sat = _clamp64(s)
    return c, sat


def _ax_mul_normative(a: int, b: int) -> tuple:
    p = a * b
    q, rem = divmod(p, 1 << 32)
    r32 = rem & 0xFFFFFFFF
    G = (r32 >> 31) & 1; R = (r32 >> 30) & 1; S = 1 if r32 & 0x3FFFFFFF else 0
    if G and (R or S or (q & 1)):
        q += 1
    clamped, sat = _clamp64(q)
    return clamped, r32 != 0, sat


def _ax_emit_o1(x: int, theta: int, cap: int) -> tuple:
    fl = {k: False for k in ("div_zero", "input_range", "burst_crop", "saturated", "truncated")}
    if theta <= 0:
        fl["div_zero"] = True; return x, 0, fl
    if x < 0:
        fl["input_range"] = True; return x, 0, fl
    emit = x // theta
    if emit > cap:
        emit = cap; fl["burst_crop"] = True
    drain, trunc, sat_m = _ax_mul_normative(emit << 32, theta)
    if trunc: fl["truncated"] = True
    if sat_m: fl["saturated"] = True
    xn, sat_a = _ax_add_sat(x, -drain)
    if sat_a: fl["saturated"] = True
    return xn, emit, fl


def _splitmix64(state: list) -> int:
    z = (state[0] + 0x9e3779b97f4a7c15) & 0xFFFFFFFFFFFFFFFF
    state[0] = z
    z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & 0xFFFFFFFFFFFFFFFF
    return z ^ (z >> 31)


def _to_i64(x: int) -> int:
    x &= 0xFFFFFFFFFFFFFFFF
    return x - (1 << 64) if x >= (1 << 63) else x


def run_k0_full_python(n: int = 200_000) -> dict:
    """Exécute la suite de test K0-Full normative en Python pur."""
    seed = 0xA10 + 0x123456789abcdef0
    state = [seed & 0xFFFFFFFFFFFFFFFF]
    h = hashlib.sha256()

    t0 = time.perf_counter()
    for _ in range(n):
        a = _to_i64(_splitmix64(state)); b = _to_i64(_splitmix64(state))
        x = _to_i64(_splitmix64(state)); theta = _to_i64(_splitmix64(state) | 1)
        cap = (_splitmix64(state) % 128) + 1

        r_add, sat_a = _ax_add_sat(a, b)
        r_mul, trunc_m, sat_m = _ax_mul_normative(a, b)
        x2, emit, fl = _ax_emit_o1(x, theta, cap)

        st = 0
        if sat_a: st |= 1
        if sat_m: st |= 1
        if trunc_m: st |= 2
        if fl["burst_crop"]: st |= 4
        if fl["input_range"]: st |= 8
        if fl["div_zero"]: st |= 16
        if fl["saturated"]: st |= 1
        if fl["truncated"]: st |= 2

        h.update(struct.pack("<q", r_add))
        h.update(struct.pack("<q", r_mul))
        h.update(struct.pack("<q", x2))
        h.update(struct.pack("<q", emit))
        h.update(struct.pack("<I", st))

    elapsed = time.perf_counter() - t0
    digest = h.hexdigest()
    return {"hash": digest, "elapsed_s": round(elapsed, 3), "n": n,
            "match_reference": digest == REFERENCE_HASH_K0_FULL}


def build_cell_record(lang: str, hash_val: str, elapsed_s: float,
                      n: int, compiler_info: str = "") -> dict:
    return {
        "variant": "K0-Full",
        "spec_version": "2.5",
        "n_iterations": n,
        "lang": lang,
        "platform": platform.machine(),
        "platform_system": platform.system(),
        "python_version": platform.python_version() if lang == "Python" else None,
        "compiler_info": compiler_info,
        "hash": hash_val,
        "match_reference": hash_val == REFERENCE_HASH_K0_FULL,
        "elapsed_s": elapsed_s,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def aggregate_matrix(results_dir: Path) -> dict:
    """Agrège tous les fichiers cell_*.json et vérifie la matrice."""
    cells = []
    for fp in sorted(results_dir.glob("cell_*.json")):
        with open(fp) as f:
            cells.append(json.load(f))

    if not cells:
        print("Aucun fichier cell_*.json trouvé dans", results_dir)
        return {}

    print(f"\n{'='*65}")
    print(f"MATRICE DE CONFORMANCE K0 — {len(cells)} cellules")
    print(f"{'='*65}")
    print(f"\nRéférence : {REFERENCE_HASH_K0_FULL[:32]}...")
    print()

    all_match = True
    for c in cells:
        match = c.get("match_reference", False)
        mark = "✅" if match else "❌"
        print(f"  {c['lang']:10} / {c['platform']:12} → {c['hash'][:16]}... {mark}")
        if not match:
            all_match = False

    # Hash de manifest
    manifest_content = json.dumps(sorted(c["hash"] for c in cells)).encode()
    manifest_sha = hashlib.sha256(manifest_content).hexdigest()

    print(f"\n  Manifest SHA-256 : {manifest_sha[:32]}...")
    print(f"\n  Résultat : {'✅ CONFORMANCE K0-Cross-Platform' if all_match else '❌ DIVERGENCE DÉTECTÉE'}")

    result = {
        "cells": cells,
        "all_match_reference": all_match,
        "manifest_sha256": manifest_sha,
        "n_cells": len(cells),
        "reference_hash": REFERENCE_HASH_K0_FULL,
    }
    out = results_dir / "matrix_manifest.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Manifest → {out}")
    return result


def main():
    parser = argparse.ArgumentParser(description="K0 Cross-Platform Matrix — Exp. 2")
    parser.add_argument("--lang", choices=["python"], default="python",
                        help="Langage à tester (Python autonome ; C et Rust via outils externes)")
    parser.add_argument("--report-c-hash", metavar="HASH",
                        help="Rapporter un hash C obtenu en dehors de ce script")
    parser.add_argument("--report-rust-hash", metavar="HASH",
                        help="Rapporter un hash Rust obtenu en dehors de ce script")
    parser.add_argument("--aggregate", metavar="DIR",
                        help="Agréger tous les fichiers cell_*.json du répertoire spécifié")
    parser.add_argument("--out", default=str(_OUTDIR), help="Répertoire de sortie")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    if args.aggregate:
        aggregate_matrix(Path(args.aggregate))
        return

    results = {}

    # Test Python (autonome)
    if args.lang == "python":
        print("=== K0-Full Python (N=200000) ===")
        res = run_k0_full_python()
        print(f"Hash  : {res['hash']}")
        print(f"Ref   : {REFERENCE_HASH_K0_FULL}")
        print(f"Match : {'✅ OUI' if res['match_reference'] else '❌ NON'}")
        print(f"Durée : {res['elapsed_s']}s")
        cell = build_cell_record("Python", res["hash"], res["elapsed_s"], res["n"])
        fname = f"cell_python_{platform.machine().lower()}.json"
        with open(out_dir / fname, "w") as f:
            json.dump(cell, f, indent=2)
        print(f"→ {out_dir / fname}")
        results["python"] = cell

    # Rapport hash C externe
    if args.report_c_hash:
        print(f"\n=== K0-Full C (rapporté) ===")
        c_hash = args.report_c_hash.strip()
        match = c_hash == REFERENCE_HASH_K0_FULL
        print(f"Hash  : {c_hash}")
        print(f"Match : {'✅ OUI' if match else '❌ NON'}")
        cell = build_cell_record("C", c_hash, 0.0, 200_000,
                                 compiler_info="external (see compilation log)")
        fname = f"cell_c_{platform.machine().lower()}.json"
        with open(out_dir / fname, "w") as f:
            json.dump(cell, f, indent=2)
        print(f"→ {out_dir / fname}")
        results["c"] = cell

    # Rapport hash Rust externe
    if args.report_rust_hash:
        print(f"\n=== K0-Full Rust (rapporté) ===")
        r_hash = args.report_rust_hash.strip()
        match = r_hash == REFERENCE_HASH_K0_FULL
        print(f"Hash  : {r_hash}")
        print(f"Match : {'✅ OUI' if match else '❌ NON'}")
        cell = build_cell_record("Rust", r_hash, 0.0, 200_000,
                                 compiler_info="external (see cargo build log)")
        fname = f"cell_rust_{platform.machine().lower()}.json"
        with open(out_dir / fname, "w") as f:
            json.dump(cell, f, indent=2)
        print(f"→ {out_dir / fname}")
        results["rust"] = cell

    if not results:
        print("Aucun test exécuté. Utiliser --lang python, --report-c-hash, ou --aggregate.")
        parser.print_help()


if __name__ == "__main__":
    main()
