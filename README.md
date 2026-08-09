# K0 — Déterminisme Bit-Exact pour les SNN via Arithmétique Entière Normative

**Public reproduction package for ArithSpec / K0 — Zenodo update 2026-08-08**

Repository:

```text
https://github.com/Prev56/arithspec-k0-public-repro
```

Ce dépôt contient uniquement les artefacts publics K0 nécessaires à la reproduction des résultats explicitement listés.

It does not contain private project logic, internal governance files, private parameters, orchestration scripts, credentials, tokens, or local machine paths.

## Public repository boundary

This repository is the **public reproduction repository** for K0/ArithSpec conformance artifacts:

```text
https://github.com/Prev56/arithspec-k0-public-repro
```

The repository `Prev56/arithspec-ax-k0` is a private/internal working repository and is not the public reproduction source. Public reproduction, citation, licensing, and Zenodo references should point to this repository and to the Zenodo DOIs listed below.

Public Zenodo records:

| Record | DOI | Purpose |
|---|---|---|
| ArithSpec P1 | https://doi.org/10.5281/zenodo.20723009 | Normative arithmetic substrate paper, version DOI |
| ArithSpec P1 concept | https://doi.org/10.5281/zenodo.20723008 | Concept DOI for all P1 versions |
| Record A | https://doi.org/10.5281/zenodo.21749447 | Per-tick certification |
| Record B | https://doi.org/10.5281/zenodo.21750037 | Internal/decision margins and low precision |
| Record D | https://doi.org/10.5281/zenodo.21750043 | Rate-level robustness |
| Record E | https://doi.org/10.5281/zenodo.21750054 | Quantization invariance in public LIF-model experiments |

## Vue d'ensemble

K0 est une spécification arithmétique et une suite de tests de conformance pour les réseaux de neurones impulsionnels (SNN), garantissant la **reproductibilité bit-pour-bit** indépendamment du langage, compilateur et architecture matérielle.

**Problème résolu** : Les SNN flottants (IEEE-754) produisent des trajectoires divergentes entre x86-64 et ARM aarch64 (même seed, même réseau, mêmes paramètres). Cette divergence compromet la reproductibilité des résultats scientifiques et la certification des systèmes embarqués.

**Solution K0** : Remplacer tout le chemin de calcul par des entiers normés Q32.32 ou Q16.16, avec arrondi ties-to-even (RNE) et saturation explicite. Résultat : un hash SHA-256 identique sur toute plateforme conforme.

### Hash de conformance certifié (K0-Full, N=200 000)

```
45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d
```

| Plateforme | Langage | Compilateur / Runtime | -O0 | -O2 | Status |
|---|---|---|---|---|---|
| x86-64 / Windows | C | GCC 15.2.0 (MinGW64) | oui | oui | reproduced |
| x86-64 / Windows | Python | 3.11.0rc2 | n/a | oui | reproduced |
| aarch64 / Linux (Pi 5) | C | GCC 14.2.0 (Debian) | oui | oui | reproduced |
| aarch64 / Linux (Pi 5) | Python | 3.13.5 | n/a | oui | reproduced |
| aarch64 / Linux | Rust | TBD | n/a | n/a | pending |

**O0 == O2 sur x86-64 ET aarch64** → absence d'undefined behavior confirmée cross-architecture.

---

## Structure du dépôt

```
k0-deterministic-snn/
├── spec/
│   ├── K0_NORMATIVE_v2.5.md    ← Spécification figée (normative)
│   └── CONFORMANCE.md           ← Critères et vecteurs de test
├── csrc/                        ← Implémentation C de référence (K0-Full)
│   ├── ax.h / ax.c              ← Arithmétique K0-Full (INT64 Q32.32)
│   └── ax_k0_test.c             ← Suite de test canonique (SHA-256)
├── python/
│   └── k0_full_test.py          ← Port Python K0-Full (conformant)
├── experiments/
│   ├── baseline_divergence/     ← Exp. 1 : divergence flottant vs K0
│   ├── k0_cross_platform/       ← Exp. 2 : matrice 3×3 langages × plateformes
│   ├── cost_characterization/   ← Exp. 3 : surcoût normativité
│   └── scaling/                 ← Exp. 4 : passage à l'échelle 64→100k neurones
├── results/                     ← Résultats des expériences
├── figures/                     ← Figures pour publication
└── paper/                       ← Texte du papier
```

---

## Démarrage rapide

### Test de conformance C

```bash
cd csrc/
# Linux / macOS / MinGW-W64 :
gcc -O2 -std=c11 ax.c ax_k0_test.c -o k0_test
./k0_test
# → AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

# Sur Pi aarch64 — même commande, même hash attendu
```

### Test de conformance Python

```bash
cd python/
python k0_full_test.py
# → AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d
```

### Expérience de divergence baseline

```bash
cd experiments/baseline_divergence/
python baseline_divergence.py --mode quick   # 200 ticks, rapide
python baseline_divergence.py --mode full    # 10 000 ticks, génère CSV

# Sur Pi — copier le fichier JSON et comparer :
python baseline_divergence.py --mode compare \
    --file1 results/results_amd64_full.json \
    --file2 results/results_aarch64_full.json
```

---

## Résultats clés (Phase 1)

| Expérience | Résultat |
|---|---|
| Divergence flottant (ordre alt vs std) | Tick 11 / 200 ticks — 34 spikes divergents |
| K0-Lite S2 double-run | **PASS** — hash identique |
| K0-Full C vs Python | **IDENTIQUES** — `45ff9803...` |

---

## Variantes K0

| Variante | Format | Usage | Hash de référence |
|---|---|---|---|
| **K0-Full** | INT64 Q32.32 | PC/serveur, référence normative | `45ff9803...` |
| **K0-Lite** | INT32 Q16.16 | Edge embarqué (Pi, Pico) | `e1606bef1b34afe155adeace4aae7fd2aa22f0236ada22a61dd71631baae050a` |

K0-Full et K0-Lite sont chacune bit-exactes à elles-mêmes cross-platform. Elles **ne sont pas** bit-exactes entre elles (variantes distinctes).

---

## Honnêteté scientifique — Ce que K0 ne revendique PAS

1. K0 n'est **pas** le premier SNN entier (L-SPINE, Loihi 2, Full Integer Training 2025 existent).
2. K0 n'est **pas** biologiquement fidèle.
3. K0 n'est **pas** plus rapide que le flottant (au contraire, voir Expérience 3).
4. K0 **n'est pas** une découverte en neuroscience.
5. La nouveauté revendiquée est étroite : **reproductibilité bit-exacte cross-platform SANS accepter de seuil d'erreur**, contrairement aux travaux précédents qui tolèrent des divergences bornées.
6. K0 se limite aux artefacts publics nécessaires aux résultats explicitement listés.

---

## Licence

- Code (`csrc/`, `python/`, `rust/`, `ros2/`, scripts de reproduction) : [AGPL-3.0-only](LICENSE)
- Spécification (`spec/`) : CC BY 4.0
- Papiers, figures, rapports, expériences et résultats (`paper/`, `figures/`, `results/`, `experiments/`, rapports Markdown) : CC BY 4.0

See [PUBLIC_SCOPE_AND_CITATION.md](PUBLIC_SCOPE_AND_CITATION.md) for the public/private boundary, citation guidance, and license map.
See [NOTICE](NOTICE) for the license scope notice.

