# PHASE 2 — Checklist de certification ARM aarch64

**Objectif** : compléter la matrice de conformance K0 sur Pi 5 (aarch64-linux)
**Durée estimée** : 1–3 jours (selon disponibilité hardware)
**Condition de publication** : ≥4 cellules sur 9, dont C+Python × x86 + aarch64

---

## Prérequis hardware

- [ ] Raspberry Pi 5 (aarch64-linux, 64-bit OS impératif — pas armv7)
- [ ] Python 3.10+ installé (`python3 --version`)
- [ ] GCC installé (`gcc --version`)

Vérification rapide :
```bash
uname -m        # → aarch64
python3 --version
gcc --version
```

---

## Étape 1 — Copier le dépôt sur Pi

```bash
# Option A : git clone (si le dépôt est publié)
git clone http.]/k0-deterministic-snn.git
cd k0-deterministic-snn

# Option B : rsync depuis x86 (si non publié)
rsync -avz k0-deterministic-snn/ pi@raspberrypi5:~/k0-deterministic-snn/
```

---

## ✈ Séquence dès accès Pi 5 — copy-paste ready

Coller ce bloc entier dans le terminal Pi 5. Résultats attendus en une ligne chacun.
Colle la sortie complète en retour pour traitement immédiat.

```bash
# 1. Sanité architecture
uname -m && python3 --version && gcc --version

# 2. Endianness
python3 -c "import sys; print(sys.byteorder)"

# 3. Hash C — O0 d'abord (contrôle UB — doit être identique à O2)
cd ~/k0-deterministic-snn/csrc
gcc -O0 -std=c11 ax.c ax_k0_test.c -o k0_O0 && ./k0_O0
# Attendu : AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

# 4. Hash C — O2 (résultat de publication)
gcc -O2 -std=c11 ax.c ax_k0_test.c -o k0_O2 && ./k0_O2
# Attendu : AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

# 5. Hash Python
cd ~/k0-deterministic-snn/python && python3 k0_full_test.py
# Attendu : AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

# 6. ★ Divergence float (résultat Figure 1 du papier)
cd ~/k0-deterministic-snn/experiments/baseline_divergence
python3 baseline_divergence.py --mode full
```

**Note O0==O2** : si les deux hashs C sont identiques, c'est un résultat publiable
(§4.4 du papier) — absence d'UB exploitée par l'optimiseur, confirmée cross-architecture.
Sur x86-64 : O0==O2==`45ff9803...` ✅ déjà confirmé (2026-06-07).

---

## ★ Ordre d'exécution recommandé (par priorité scientifique)

```
JOUR 1 matin  : étape 1 (clone) + étape 1b (endianness) + étape 2 (C hash ARM)
JOUR 1 après  : étape 3 (Python hash ARM) → condition arXiv satisfaite si PASS
JOUR 1 soir   : étape 7 ★★ (divergence float cross-platform) → Figure 1 du papier
JOUR 2        : étapes 4, 5, 6 (benchmark, matrice, agrégation)
```

**Pourquoi étape 7 avant étapes 4–6** : l'aarch64 utilise FMADD (fused multiply-add)
là où x86 sépare FMUL + FADD. Le tick de première divergence peut différer entre
architectures — ce serait un résultat bonus non planifié : la divergence flottante
elle-même n'est pas reproductible cross-architecture, ce qui renforce K0.

---

## Étape 1b — Vérification endianness (critique avant tout hashing)

```bash
python3 -c "import sys; print(sys.byteorder)"
# → 'little' attendu (Pi 5 Linux = little-endian)

# Vérifier aussi en C :
python3 -c "import struct; print(struct.pack('<q', 1).hex())"
# → 0100000000000000 (little-endian confirmé)
```

**Note** : `ax_k0_test.c` sérialise explicitement en little-endian via
`b[i]=(uint8_t)(v>>(8*i))` — pas un `memcpy` implicite. C'est correct et
portable. Sur un système big-endian (MIPS, PowerPC, s390x), le hash serait
différent : K0 est little-endian **par spécification** (voir `CONFORMANCE.md §8`).

---

## Étape 2 — Test C sur aarch64

```bash
cd csrc/
gcc -O2 -std=c11 ax.c ax_k0_test.c -o k0_test
./k0_test
```

**Résultat attendu** (IDENTIQUE à x86-64) :
```
AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d
```

✅ PASS : même hash → Cellule (C, aarch64) certifiée  
❌ FAIL : hash différent → suivre le **protocole de diagnostic** ci-dessous

### Protocole si le hash diverge sur ARM

```bash
# Étape A : tester -O0 vs -O2
gcc -O0 -std=c11 ax.c ax_k0_test.c -o k0_O0 && ./k0_O0
# → Si O0 == 45ff9803 mais O2 ≠ : undefined behavior (UB) probable
# → Chercher les multiplications INT64 sans __int128

# Étape B : détecter l'UB avec sanitizer
gcc -O1 -std=c11 -fsanitize=undefined ax.c ax_k0_test.c -o k0_ub && ./k0_ub
# → Toute UB sera reportée au runtime avec position dans le code

# Étape C : si UB trouvée
# → c'est une correction de spec, pas une défaite
# → Documenter dans CONFORMANCE.md, corriger ax.c, re-hasher sur les deux platforms
# → Le nouveau hash devient la référence (invalide l'ancienne — documenter le changement)
```

**Lecture d'un échec** : un hash divergent sur ARM avec -O0 mais pas -O2 indique
que le compilateur exploite une UB pour optimiser différemment. C'est un bug
corrigible dans `ax.c`, pas une limite de la spécification K0.

---

## Étape 3 — Test Python sur aarch64

```bash
cd python/
python3 k0_full_test.py
```

**Résultat attendu** :
```
AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d
```

---

## Étape 4 — Test divergence baseline sur aarch64

```bash
cd experiments/baseline_divergence/
python3 baseline_divergence.py --mode full
```

Sauvegarder le JSON généré : `results/results_aarch64_full.json`

---

## Étape 5 — Benchmark C sur aarch64

```bash
cd csrc/
gcc -O2 -std=c11 ax_bench.c -o ax_bench -lm
./ax_bench
```

Sauvegarder la sortie dans `results/bench_aarch64.txt`.
À comparer avec x86-64 pour la section résultats du papier.

---

## Étape 6 — Matrice cross-platform

Rapporter les résultats dans le script Python :

```bash
# Sur Pi (générer cell JSON)
cd experiments/k0_cross_platform/
python3 k0_cross_platform_matrix.py --lang python --out results/
python3 k0_cross_platform_matrix.py \
    --report-c-hash 45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d \
    --out results/

# Rapatrier les fichiers cell_*_aarch64.json sur x86
# puis agréger :
python3 k0_cross_platform_matrix.py --aggregate results/
```

---

## Étape 7 — Divergence baseline cross-platform

Sur x86-64 :
```bash
python baseline_divergence.py --mode full
# → results/results_amd64_full.json
```

Sur aarch64 :
```bash
python3 baseline_divergence.py --mode full
# → results/results_aarch64_full.json
```

Comparer sur x86-64 :
```bash
python baseline_divergence.py --mode compare \
    --file1 results/results_amd64_full.json \
    --file2 results/results_aarch64_full.json
```

**Hypothèse testable** : 
- `hash_float_standard(x86) ≠ hash_float_standard(aarch64)` → divergence cross-platform confirmée
- `hash_k0_lite(x86) == hash_k0_lite(aarch64)` → invariant K0 confirmé

---

## Critères de succès Phase 2a (suffisant pour soumettre)

| Critère | Résultat attendu |
|---|---|
| C/aarch64 hash | `45ff9803...` ✅ |
| Python/aarch64 hash | `45ff9803...` ✅ |
| Matrice 4/9 | C+Python × x86+aarch64 ✅ |
| Divergence float cross-platform | hash(x86) ≠ hash(aarch64) ✅ |
| K0 cross-platform | hash(x86) == hash(aarch64) ✅ |

**Condition de soumission arXiv** : les 5 critères ci-dessus PASS.

---

## Phase 2b (optionnel avant soumission, fort pour révision)

**Rust port K0-Full** :
- Créer `rust/src/lib.rs` avec `k0_mul_normative(a: i64, b: i64) -> i64`
- Utiliser `i128` pour le produit intermédiaire
- Test : `cargo test k0_conformance -- --nocapture`
- Résultat attendu : même hash `45ff9803...`

**RP2040 (K0-Lite)** :
- Installer `pico-sdk` + `gcc-arm-none-eabi`
- Compiler `csrc/ax_k0_lite_test.c` (à créer) pour K0-Lite
- Taille SRAM: 264 KB → réseau N=16 neurones max en K0-Lite

---

## Checklist de rapport Phase 2

Après certification aarch64, mettre à jour :

- [ ] `spec/CONFORMANCE.md` §7 — ajouter les cellules aarch64
- [ ] `experiments/k0_cross_platform/results/matrix_manifest.json` — régénérer
- [ ] `paper/K0_paper_draft_v0.1.md` §4.2 — compléter la table Phase 2
- [ ] `README.md` — mettre à jour le tableau de certification
- [ ] `agents/AGENT_LIVE_STATE.md` — `LAST_COMPLETED=K0_PUBLICATION_PHASE2_AARCH64`

---

## Note : Pi 5 vs Pi 4 vs Pi Zero

| Modèle | Arch | RAM | GCC | Recommandation |
|---|---|---|---|---|
| **Pi 5** | aarch64 | 4-8 GB | ✅ | **Recommandé** pour Phase 2 |
| Pi 4 | aarch64 | 4 GB | ✅ | OK |
| Pi Zero 2 | aarch64 | 512 MB | ✅ | OK (lent) |
| Pi Zero (v1) | armv6 (32-bit) | 512 MB | Partiel | **NON** — 32-bit insuffisant pour K0-Full |

K0-Full requiert int64 natif → architecture 64-bit obligatoire.
K0-Lite (INT32) fonctionne sur Pi Zero v1, mais ce n'est pas K0-Full.
