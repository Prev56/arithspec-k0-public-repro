# AUDIT_REPORT_K0_COMPLET

**Projet** : `k0-deterministic-snn` (Phase 1 + 2a + 2b + 2c)
**Date d'audit** : 2026-06-08 · **Auditeur** : agent · **Méthode** : ré-exécution live + lecture artefacts
**Constante** : aucun hash de référence modifié (`45ff9803…`, `e1606bef…`, `908e6da8…` préservés).

---

## État des hashes (vérifié)

### K0-Full — référence `45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d`

| Lang | Plateforme | Hash obtenu | Référence | Source | Status |
|---|---|---|---|---|---|
| C | x86-64 Win | `45ff9803…` | `45ff9803` | **LIVE** (gcc 15.2.0 -O2 MinGW) | ✅ |
| Python | x86-64 Win | `45ff9803…` | `45ff9803` | **LIVE** (CPython 3.11) | ✅ |
| Rust | x86-64 Win | `45ff9803…` | `45ff9803` | **LIVE** (cargo 1.92.0, x86_64-pc-windows-gnu) | ✅ |
| C | aarch64 Pi5 | `45ff9803…` | `45ff9803` | manifeste Phase 2a (GCC 14.2.0 -O0 et -O2) | ✅ |
| Python | aarch64 Pi5 | `45ff9803…` | `45ff9803` | manifeste Phase 2a (Python 3.13.5) | ✅ |
| Rust | aarch64 Pi5 | `45ff9803…` | `45ff9803` | manifeste Phase 2b (rustc 1.95.0) | ✅ |

> Note : le rapport de session indiquait Rust `rustc 1.95.0` ; le binaire x86 ré-exécuté ici provient de
> `cargo 1.92.0 (MSYS2)`. Le **hash est identique** → l'écart de version d'outil ne change pas la sortie
> normative (résultat attendu, c'est précisément la propriété visée). Écart documenté, non bloquant.

### K0-Lite — référence `e1606bef1b34afe155adeace4aae7fd2aa22f0236ada22a61dd71631baae050a`

| Lang | Plateforme | Hash | Source | Status |
|---|---|---|---|---|
| Rust | x86-64 Win | `e1606bef…` | cell Phase 2c | ✅ |
| Rust | aarch64 Pi5 | `e1606bef…` | cell Phase 2c | ✅ |
| C++ | aarch64 Pi5 | `e1606bef…` | cell Phase 2c (bug INT32_MIN résolu) | ✅ |

**Bilan hashes** : 6/6 cellules K0-Full conformes (3 ré-vérifiées live, 3 sur artefact Pi) ; 3/3 K0-Lite.
Aucune divergence.

---

## État TLA+

- **Fichiers présents** : `formal/K0Composition.tla`, `formal/K0Composition.cfg`, `formal/states/…` (2 runs horodatés).
- **TLC exécuté** : **OUI**, et **re-vérifié live** ce jour (TLC2 v2.19, OpenJDK 21.0.5, `tla2tools.jar`).
- **Résultat** : `Model checking completed. No error has been found.` — **39 366 états générés, 19 683 distincts**, exhaustif sur le domaine Q16.16 `{-32767, 0, 32767}`, ~0,95 s.
- **Propriétés vérifiées (5/5)** : `LeftIdentityBias`, `RightIdentityBias`, `LeftIdentityWeight`, `RightIdentityWeight`, `StickyStatus`.
- **Non-revendiqué (honnête)** : `AssocBias` — l'addition saturante **n'est pas** associative (contre-exemple documenté). Correctement exclu des invariants.
- **Manquant avant cet audit** : `formal/tlc_results/` n'existait pas → **créé** (`tlc_output.txt` sauvegardé).
- **Artefact JSON** : `tlc_k0composition_result.json` présent et cohérent avec le run live.

---

## État ROS 2

- **Package créé** : OUI — `ros2/k0_snn_controller/` (`CMakeLists.txt`, `package.xml`, `src/k0_snn_node.cpp`).
- **Node** : publie `/k0_snn/output`, souscrit `/k0_snn/input`, K0-Lite INT32 Q16.16 portée du Rust ; mode `determinism_test` intégré (`k0_determinism_run`, double-run).
- **Build ROS testé** : NON sur cette machine (rclcpp/ROS 2 Jazzy indisponible hors Pi) — **non bloquant**.
- **Test déterminisme exécutable** : **ABSENT avant audit** (pas de standalone hors-ROS, pas de `ros2/results/`, aucun hash enregistré).
  → **Corrigé** : `ros2/k0_ros_determinism_standalone.cpp` (reprend **verbatim** `k0_determinism_run`), compilé g++ -O2, **exécuté live**.
- **Hash double-run** : `5ce3c251361ec59e982c3ca6f4549343f8783aa1b39428a09b8510f35350a3cf` (N=1000), **run1==run2** et **stable inter-process**. Enregistré dans `ros2/results/k0_ros2_determinism.json`.

---

## État de la matrice de certification

- `matrix_manifest.json` (K0-Full) : `n_cells=7`, `all_match_reference=true`, `manifest_sha256=1b2035a9…`. **Valide**, épinglé par `arxiv_checklist.py`. **Non modifié**.
- **Constat** : ce manifeste **n'inclut pas** les 3 cellules **K0-Lite** Phase 2c (présentes en `cell_*k0lite*.json`) → manifeste **incomplet** vis-à-vis du travail réel.
  → **Corrigé** sans casser l'existant : nouveau `matrix_manifest_k0lite.json` (`n_cells=3`, `all_match=true`, `manifest_sha256=d8dc8f47…`).
- **Cible « 9/9 » (grille K0-Full 3×3)** : **non atteignable** en l'état — pas d'hôte **Linux x86-64** disponible, et la cellule **RP2040 physique** est en attente (hardware). Les deux sont **non bloquants** (seuil défini = 7/9 ; RP2040 cross-compile `thumbv6m-none-eabi` déjà PASS en `cargo check`).
- **État réel combiné** : **10 cellules certifiées** = 7 K0-Full + 3 K0-Lite, + 5 lois TLA+ + 1 déterminisme ROS 2.

---

## État du papier

- **Version** : en-tête `Draft v0.4 — 2026-06-08` ; **pied de page incohérent** (`draft-v0.1 — 2026-06-07`). → à corriger.
- **Sections présentes** : Abstract, §1 (1.1–1.3, gap Brian2/SpikingJelly posé), §2 (spec, GRS+RNE), §3 (C/Python/Rust), §4.1 divergence (tick 11), §4.2 matrice, §4.3 coût, §4.4 O0 vs O2, §4.5 bench Rust, §4.6 NIR-K0 (+ AX_TRUNCATED observability), §5 (5.1–5.3, limitations 1–8), §6 conclusion, Réfs, Annexes A/B.
- **Sections manquantes vs plan** :
  - ❌ **§ TLA+ (vérification formelle)** — résultats TLC existent mais **absents du papier**.
  - ❌ **§ ROS 2 (déterminisme robotique)** — node existe mais **pas de section**.
  - ❌ **Figure 3 — table AX_TRUNCATED** par étape (le §4.6 en parle en prose, pas de table).
- **Références** : **stub** (`[REF]`, « To be completed ») — Yik/NeuroBench, Pedersen/NIR, Goldberg, Stimberg/Brian2, Eshraghian/snnTorch, L-SPINE, Full Integer SNN **manquants**.
- **Conclusion §6** : périmée (« Phase 2 will extend to aarch64 » alors qu'aarch64 est **certifié**).
- **Abstract** : solide ; mentionne C+Python mais **pas Rust** dans la phrase du hash ; ne mentionne pas la **vérification formelle TLA+**.

---

## Points bloquants / à corriger avant arXiv

| # | Point | Gravité | Action |
|---|---|---|---|
| 1 | Références en stub `[REF]` | **BLOQUANT** publication | Compléter la bibliographie (7 réfs) |
| 2 | Pas de section TLA+ dans le papier | Majeur | Ajouter § vérification formelle (5 invariants, 19 683 états) |
| 3 | Pas de section ROS 2 | Majeur | Ajouter § déterminisme ROS 2 (hash `5ce3c251`) |
| 4 | Figure 3 sans table AX_TRUNCATED | Mineur | Ajouter la table par étape |
| 5 | Version pied de page incohérente | Mineur | Aligner sur v1.0 |
| 6 | Conclusion périmée (aarch64) | Mineur | Mettre à jour l'état réel |
| 7 | Manifeste K0-Lite absent | Mineur (corrigé) | ✅ `matrix_manifest_k0lite.json` créé |
| 8 | `formal/tlc_results/` absent | Mineur (corrigé) | ✅ `tlc_output.txt` sauvegardé |
| 9 | Test déterminisme ROS 2 absent | Majeur (corrigé) | ✅ standalone créé + exécuté |

**Non bloquants (seuil défini)** : grille 9/9 K0-Full (pas d'hôte Linux x86-64), RP2040 physique.

---

## Verdict d'audit

**Base technique SAINE et reproductible.** Les revendications centrales (bit-exactitude cross-platform
K0-Full sur 3 langages × 2 ISA, K0-Lite sur 3 implémentations, 5 lois de composition mécanisées en TLA+,
déterminisme ROS 2) sont **toutes vérifiées**. Les manques sont **éditoriaux** (papier : références, 2 sections,
cohérence) et **non fabriqués** : ils sont comblés en ÉTAPE 3–4 avec des artefacts réellement exécutés.
État : **ASSEMBLAGE REQUIS**, pas de résultat scientifique à corriger.
