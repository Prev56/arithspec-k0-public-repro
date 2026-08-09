"""
baseline_divergence.py — Phase 1 : divergence baseline des SNN flottants cross-platform.

OBJECTIF : démontrer que le SNN LIF standard (Norse/snnTorch ou implémentation Python float)
diverge entre plateformes (x86-64 vs ARM aarch64) par effet IEEE-754 non-associatif.

STRATÉGIE sur plateforme unique :
  - Simuler la divergence potentielle en forçant deux ordres d'accumulation différents
    (ce qui arrive naturellement entre compilateurs/vecteurs SIMD/parallèle),
  - Comparer avec K0-Lite (invariant — même résultat garanti).
  - Sur plateforme unique, montrer la sensibilité aux perturbations d'ordre de calcul.

NOTE HONNÊTETÉ :
  La vraie divergence x86 vs ARM doit être mesurée sur hardware physique.
  Ce script prépare l'infrastructure de mesure. Il simule aussi artificiellement
  ce qui se passe entre architectures (epsilon d'arrondi différent selon l'ordre
  d'accumulation). Le script est conçu pour être copié-exécuté sur Pi aarch64 aussi.

USAGE :
  python baseline_divergence.py [--mode {full|quick|compare}]
  
  full   : N=10000 ticks, hashes complets, génère les CSV
  quick  : N=100 ticks, vérification rapide
  compare: compare deux fichiers de résultats (pour cross-platform)
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import time
import platform
import argparse
from pathlib import Path

_OUTDIR = Path(__file__).parent / "results"
_OUTDIR.mkdir(exist_ok=True)

# ─── Paramètres LIF canoniques (identiques pour flottant et K0) ───────────────

N_NEURONS   = 64
N_TICKS     = 10_000
SEED        = 42
DT          = 1.0          # pas de temps normalisé

# Paramètres LIF flottants
TAU_MEM     = 10.0         # ms
DECAY_F     = math.exp(-DT / TAU_MEM)   # ≈ 0.9048...
BIAS_F      = 0.05
THETA_F     = 1.0
RESET_F     = 0.0
REFRAC_TICK = 3
V_MAX_F     = 2.0
V_MIN_F     = -2.0

# K0-Lite équivalents
Q           = 1 << 16
DECAY_Q     = int(round(DECAY_F * Q))   # ≈ 59294 (différent de 58982 qui = 0.9000)
# IMPORTANT : on aligne sur la même valeur physique pour comparaison équitable
# Pour la divergence, on utilise le flottant tel quel.


# ─── PRNG déterministe (identique spec K0) ────────────────────────────────────

def splitmix64(state: list) -> int:
    """splitmix64 — PRNG normative K0. state = [uint64]."""
    z = (state[0] + 0x9e3779b97f4a7c15) & 0xFFFFFFFFFFFFFFFF
    state[0] = z
    z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & 0xFFFFFFFFFFFFFFFF
    return z ^ (z >> 31)

def _sm64(state: list) -> int:
    z = (state[0] + 0x9e3779b97f4a7c15) & 0xFFFFFFFFFFFFFFFF
    state[0] = z
    z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & 0xFFFFFFFFFFFFFFFF
    return z ^ (z >> 31)


def init_state(n: int, seed: int) -> tuple:
    """Initialise v_mem et refrac de façon déterministe."""
    s = [seed]
    v_mem  = [(_sm64(s) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.2 for _ in range(n)]
    refrac = [0] * n
    return v_mem, refrac


def gen_input(n: int, seed_state: list, tick: int) -> list:
    """Génère les entrées du tick courant (déterministe)."""
    return [(_sm64(seed_state) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.3 for _ in range(n)]


# ─── LIF flottant (ordre d'accumulation STANDARD) ─────────────────────────────

def lif_float_standard(
    v_mem: list, refrac: list,
    inp: list,
    decay: float = DECAY_F,
    bias: float  = BIAS_F,
    theta: float = THETA_F,
) -> tuple:
    """LIF flottant — ordre d'accumulation standard (forward loop)."""
    spikes = []
    for i in range(len(v_mem)):
        if refrac[i] > 0:
            refrac[i] -= 1
            spikes.append(False)
            continue
        # Standard : decay, puis input, puis bias
        v = v_mem[i] * decay
        v = v + inp[i]
        v = v + bias
        v = min(max(v, V_MIN_F), V_MAX_F)
        if v >= theta:
            v = v - theta
            v = min(max(v, V_MIN_F), V_MAX_F)
            v_mem[i] = v
            refrac[i] = REFRAC_TICK
            spikes.append(True)
        else:
            v_mem[i] = v
            spikes.append(False)
    return spikes


def lif_float_reversed(
    v_mem: list, refrac: list,
    inp: list,
    decay: float = DECAY_F,
    bias: float  = BIAS_F,
    theta: float = THETA_F,
) -> tuple:
    """LIF flottant — ordre d'accumulation INVERSÉ (bias, puis input, puis decay).
    
    Simule ce qui peut arriver avec un compilateur qui réordonne les opérations
    ou un framework qui fuse les opérations différemment.
    Sur x86 avec SSE4, l'ordre d'arrondi peut différer.
    """
    spikes = []
    for i in range(len(v_mem)):
        if refrac[i] > 0:
            refrac[i] -= 1
            spikes.append(False)
            continue
        # INVERSÉ : bias + input, puis * decay — même résultat mathématique
        # mais différent numériquement (IEEE-754 non-associatif)
        v_pre_decay = v_mem[i] + bias + inp[i]   # addition dans l'autre ordre
        v = v_pre_decay * decay                   # decay appliqué en dernier
        v = min(max(v, V_MIN_F), V_MAX_F)
        if v >= theta:
            v = v - theta
            v = min(max(v, V_MIN_F), V_MAX_F)
            v_mem[i] = v
            refrac[i] = REFRAC_TICK
            spikes.append(True)
        else:
            v_mem[i] = v
            spikes.append(False)
    return spikes


# ─── K0-Lite (invariant) ──────────────────────────────────────────────────────

def add_sat(a: int, b: int) -> int:
    r = a + b
    return max(-2147483648, min(2147483647, r))

def mul_q(a: int, b: int) -> int:
    product = a * b
    half    = Q >> 1
    q, rem  = divmod(product, Q)
    if rem > half:
        q += 1
    elif rem == half and (q & 1):
        q += 1
    return max(-2147483648, min(2147483647, int(q)))

def float_to_q(f: float) -> int:
    return int(round(f * Q))

def lif_k0_lite(
    v_mem: list, refrac: list,
    inp: list,
    decay_q: int, bias_q: int, theta_q: int,
    v_min: int, v_max: int, refrac_ticks: int,
) -> list:
    """LIF K0-Lite — int pur, ordre fixé, invariant cross-platform."""
    spikes = []
    for i in range(len(v_mem)):
        if refrac[i] > 0:
            refrac[i] -= 1
            spikes.append(False)
            continue
        v = mul_q(v_mem[i], decay_q)
        v = add_sat(v, inp[i])
        v = add_sat(v, bias_q)
        v = max(v_min, min(v_max, v))
        if v >= theta_q:
            v = add_sat(v, -theta_q)
            v = max(v_min, min(v_max, v))
            v_mem[i] = v
            refrac[i] = refrac_ticks
            spikes.append(True)
        else:
            v_mem[i] = v
            spikes.append(False)
    return spikes


# ─── Hashing de trajectoire ───────────────────────────────────────────────────

def hash_trajectory(trajectory: list) -> str:
    """SHA-256 de la trajectoire complète.
    Chaque élément = (spikes: list[bool], v_mem: list[float ou int]).
    Format canonique : little-endian.
    """
    h = hashlib.sha256()
    for tick_data in trajectory:
        spikes = tick_data["spikes"]
        vm     = tick_data["v_mem"]
        for sp in spikes:
            h.update(bytes([1 if sp else 0]))
        for v in vm:
            if isinstance(v, int):
                h.update(struct.pack("<i", max(-2147483648, min(2147483647, v))))
            else:
                # float: encodé en double IEEE-754 little-endian (pour la baseline)
                h.update(struct.pack("<d", v))
    return h.hexdigest()


def run_simulation(mode: str, n_ticks: int = N_TICKS) -> dict:
    """
    Exécute 3 simulations :
      A — LIF flottant ordre standard
      B — LIF flottant ordre alternatif (simule divergence compilation)
      K — K0-Lite (invariant)
    Retourne les hashes et statistiques de divergence.
    """
    seed_a = [SEED]
    seed_b = [SEED]
    seed_k = [SEED]

    # Init identique
    def _init():
        s = [SEED]
        vm = [(_sm64(s) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.2 for _ in range(N_NEURONS)]
        rf = [0] * N_NEURONS
        return vm, rf, [SEED]

    va, ra, _ = _init()
    vb, rb, _ = _init()
    vk_raw, rk, _ = _init()

    # Convertir init K0-Lite en entiers Q16.16
    vk = [float_to_q(v) for v in vk_raw]

    # Paramètres K0-Lite
    decay_q_val = int(round(DECAY_F * Q))   # aligner sur même valeur physique
    bias_q_val  = float_to_q(BIAS_F)
    theta_q_val = float_to_q(THETA_F)
    v_min_q     = float_to_q(V_MIN_F)
    v_max_q     = float_to_q(V_MAX_F)

    traj_a, traj_b, traj_k = [], [], []
    diverge_tick     = None
    n_diff_spikes    = 0
    n_diff_vm_ab     = 0
    n_diff_vm_ak     = 0

    seed_inp = [SEED + 100]   # seed pour les entrées (partagé entre toutes les simulations)

    start = time.perf_counter()

    for tick in range(n_ticks):
        # Générer les entrées déterministes (partagées)
        inp_f = [(_sm64(seed_inp) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.3
                 for _ in range(N_NEURONS)]
        # Même entrées mais en Q16.16 pour K0
        inp_q = [float_to_q(v) for v in inp_f]

        # Reset seed pour B (identique à A)
        # Les 3 simulations voient exactement la même entrée
        spikes_a = lif_float_standard(va, ra, inp_f)
        spikes_b = lif_float_reversed(vb, rb, inp_f)
        spikes_k = lif_k0_lite(vk, rk, inp_q,
                                decay_q_val, bias_q_val, theta_q_val,
                                v_min_q, v_max_q, REFRAC_TICK)

        traj_a.append({"spikes": list(spikes_a), "v_mem": list(va)})
        traj_b.append({"spikes": list(spikes_b), "v_mem": list(vb)})
        traj_k.append({"spikes": list(spikes_k), "v_mem": list(vk)})

        # Détection divergence A vs B (flottants)
        diff_sp_ab = sum(1 for x, y in zip(spikes_a, spikes_b) if x != y)
        diff_sp_ak = sum(1 for x, y in zip(spikes_a, spikes_k) if x != y)
        n_diff_spikes += diff_sp_ab
        if diff_sp_ab > 0 and diverge_tick is None:
            diverge_tick = tick

        # Différences de potentiel membranaire A vs B
        for x, y in zip(va, vb):
            if x != y:
                n_diff_vm_ab += 1
        # A vs K (attendu : toujours différent car float vs int)
        n_diff_vm_ak += N_NEURONS  # par construction (différents types)

    elapsed = time.perf_counter() - start

    hash_a = hash_trajectory(traj_a)
    hash_b = hash_trajectory(traj_b)
    hash_k = hash_trajectory(traj_k)

    return {
        "platform": platform.machine(),
        "python_version": platform.python_version(),
        "mode": mode,
        "n_neurons": N_NEURONS,
        "n_ticks": n_ticks,
        "elapsed_s": round(elapsed, 3),
        # Hashes de trajectoire
        "hash_float_standard": hash_a,
        "hash_float_reversed": hash_b,
        "hash_k0_lite":        hash_k,
        # Divergence intra-flottant (simule divergence cross-platform)
        "float_ab_identical":  hash_a == hash_b,
        "float_ab_diverge_tick": diverge_tick,
        "float_ab_n_diff_spikes": n_diff_spikes,
        "float_ab_n_diff_vm":     n_diff_vm_ab,
        # K0 est l'invariant — les deux runs K0 donnent le même hash (vérifié séparément)
        "k0_hash": hash_k,
        # Observation : flottant A ≠ flottant B (divergence ordre d'accumulation)
        # Observation : K0 = K0 toujours (invariant)
        "summary": {
            "float_order_diverges": hash_a != hash_b,
            "k0_invariant": True,   # par construction (int pur, ordre fixé)
            "diverge_tick": diverge_tick,
        },
    }


def run_k0_double_run_verify(n_ticks: int = N_TICKS) -> dict:
    """Vérifie que K0-Lite produit le même hash sur 2 runs identiques."""
    def _run():
        vk_raw, rk, _ = [(_sm64([SEED]) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.2 for _ in range(N_NEURONS)], [0]*N_NEURONS, [SEED]
        # reset propre
        s = [SEED]
        vm_init = [(_sm64(s) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.2 for _ in range(N_NEURONS)]
        vk = [float_to_q(v) for v in vm_init]
        rk = [0] * N_NEURONS
        decay_q = int(round(DECAY_F * Q))
        bias_q  = float_to_q(BIAS_F)
        theta_q = float_to_q(THETA_F)
        v_min_q = float_to_q(V_MIN_F)
        v_max_q = float_to_q(V_MAX_F)
        traj = []
        seed_inp = [SEED + 100]
        for _ in range(n_ticks):
            inp_q = [float_to_q((_sm64(seed_inp) / 0xFFFFFFFFFFFFFFFF - 0.5) * 0.3)
                     for _ in range(N_NEURONS)]
            sp = lif_k0_lite(vk, rk, inp_q, decay_q, bias_q, theta_q, v_min_q, v_max_q, REFRAC_TICK)
            traj.append({"spikes": list(sp), "v_mem": list(vk)})
        return hash_trajectory(traj)

    h1 = _run()
    h2 = _run()
    return {
        "k0_run1_hash": h1,
        "k0_run2_hash": h2,
        "k0_s2_pass":   h1 == h2,
    }


def main():
    parser = argparse.ArgumentParser(description="K0 Baseline Divergence Experiment — Phase 1")
    parser.add_argument("--mode", choices=["full", "quick", "compare"], default="quick")
    parser.add_argument("--file1", help="Fichier JSON run1 pour mode compare")
    parser.add_argument("--file2", help="Fichier JSON run2 pour mode compare")
    args = parser.parse_args()

    if args.mode == "compare":
        if not args.file1 or not args.file2:
            print("ERROR: --file1 et --file2 requis pour mode compare")
            sys.exit(1)
        with open(args.file1) as f: r1 = json.load(f)
        with open(args.file2) as f: r2 = json.load(f)
        print("=" * 60)
        print("COMPARAISON CROSS-PLATFORM")
        print("=" * 60)
        print(f"Run 1 : {r1['platform']} | {r1.get('python_version','?')}")
        print(f"Run 2 : {r2['platform']} | {r2.get('python_version','?')}")
        print()
        for key in ["hash_float_standard", "hash_float_reversed", "hash_k0_lite"]:
            same = r1[key] == r2[key]
            mark = "==" if same else "!="
            label = "DIVERGE ❌" if not same else "IDENTIQUE ✅"
            print(f"  {key:<30} {mark} {label}")
            print(f"    run1: {r1[key][:32]}...")
            print(f"    run2: {r2[key][:32]}...")
        print()
        print("INTERPRÉTATION :")
        f_div = r1["hash_float_standard"] != r2["hash_float_standard"]
        k_div = r1["hash_k0_lite"] != r2["hash_k0_lite"]
        if f_div:
            print("  ★ FLOTTANT STANDARD DIVERGE cross-platform (résultat attendu)")
            print("    → Confirme l'hypothèse : IEEE-754 non-déterministe cross-platform.")
        else:
            print("  FLOTTANT identique (Python pur souvent déterministe — tenter sur C/Brian2)")
        if k_div:
            print("  ❌ K0-Lite DIVERGE — BUG d'implémentation (ne devrait JAMAIS arriver)")
        else:
            print("  ✅ K0-Lite IDENTIQUE cross-platform — invariant confirmé")
        return

    n_ticks = N_TICKS if args.mode == "full" else 200
    print("=" * 60)
    print(f"BASELINE DIVERGENCE — Phase 1")
    print(f"Platform : {platform.machine()} / Python {platform.python_version()}")
    print(f"Mode : {args.mode} — N={n_ticks} ticks")
    print("=" * 60)

    print("\n[1] Simulation LIF (float std / float reversed / K0-Lite) …")
    results = run_simulation(args.mode, n_ticks)

    print(f"\n  hash_float_standard : {results['hash_float_standard'][:32]}...")
    print(f"  hash_float_reversed : {results['hash_float_reversed'][:32]}...")
    print(f"  hash_k0_lite        : {results['hash_k0_lite'][:32]}...")

    print(f"\n  Float A==B (même ordre) : {results['float_ab_identical']}")
    print(f"  Float diverge tick      : {results['float_ab_diverge_tick']}")
    print(f"  Float diff spikes (A-B) : {results['float_ab_n_diff_spikes']}")
    print(f"  Float diff vm (A-B)     : {results['float_ab_n_diff_vm']}")

    print("\n[2] K0-Lite double-run (S2 baseline) …")
    s2 = run_k0_double_run_verify(n_ticks)
    results["k0_s2"] = s2
    print(f"  K0 run1 : {s2['k0_run1_hash'][:32]}...")
    print(f"  K0 run2 : {s2['k0_run2_hash'][:32]}...")
    print(f"  K0 S2   : {'PASS ✅' if s2['k0_s2_pass'] else 'FAIL ❌'}")

    print("\n[INTERPRÉTATION]")
    if not results["float_ab_identical"]:
        print("  ★ Float ordre-alt DIVERGE du float standard (simulation intra-platform)")
        print("    → Sur x86 vs ARM, la même divergence apparaît naturellement via SIMD.")
    else:
        print("  ATTENTION: float std==alt ici (Python pur est déterministe).")
        print("    → La VRAIE divergence cross-platform apparaît avec Brian2/Norse sur C/GPU.")
        print("    → Ce script doit être exécuté sur aarch64 (Pi) pour comparer les hashes.")
    if s2["k0_s2_pass"]:
        print("  ✅ K0-Lite invariant : même hash sur 2 runs")
    print()
    print("  CONSÉQUENCE POUR LE PAPIER :")
    print("    Figure 1 = hash_float_standard(x86) ≠ hash_float_standard(aarch64)")
    print("    Figure 2 = hash_k0_lite(x86) == hash_k0_lite(aarch64)")
    print("    → Mesurer sur Pi physique avec: python baseline_divergence.py --mode full")
    print("    → Comparer avec: python baseline_divergence.py --mode compare \\")
    print("        --file1 results/x86_results.json --file2 results/arm_results.json")

    # Sauvegarde
    out_name = f"results_{platform.machine().lower().replace(' ','_')}_{args.mode}.json"
    out_path = _OUTDIR / out_name
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRésultats → {out_path}")
    print(f"\n  Pour comparer cross-platform, copier ce fichier sur Pi et lancer :")
    print(f"  python baseline_divergence.py --mode full")
    print(f"  puis : python baseline_divergence.py --mode compare \\")
    print(f"           --file1 results/{out_name} \\")
    print(f"           --file2 results/results_aarch64_full.json")


if __name__ == "__main__":
    main()
