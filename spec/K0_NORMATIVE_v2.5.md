# K0 — Spécification Arithmétique Normative pour SNN Déterministes
## Version 2.5 — FIGÉE (normative, immuable après cette version)

**Date de gel** : 2026-06-07  
**Auteur** : Jean-René Denoual  
**Statut** : NORMATIVE — NE PAS MODIFIER sans incrémenter la version majeure  

---

## §1 — Objectif et domaine d'application

K0 est une spécification arithmétique pour réseaux de neurones impulsionnels (SNN) garantissant la **reproductibilité bit-pour-bit** de toute trajectoire computationnelle, indépendamment du langage d'implémentation, du compilateur, de l'architecture matérielle et du niveau d'optimisation.

K0 n'est PAS une spécification d'efficacité. Son objectif premier est la **vérifiabilité formelle** : toute implémentation conforme doit produire exactement le même résultat observable (hash SHA-256 de la trajectoire complète) sur n'importe quelle plateforme physique, pour n'importe quel compilateur conforme à la norme de langage cible.

**Domaines d'application visés** :
- SNN embarqués sur systèmes critiques (robotique certifiable, médical)
- Audit et replay déterministe de comportements neuromorphiques
- Comparaison reproductible d'algorithmes SNN entre plateformes

---

## §2 — Variantes conformes

K0 définit deux variantes conformes. Elles sont **chacune** bit-exactes à elle-même cross-platform. Elles ne sont PAS bit-exactes entre elles — ce sont des variantes distinctes.

| Variante | Format | Accumulateur interne | Usage recommandé |
|---|---|---|---|
| **K0-Full** | INT64 Q32.32 | INT128 | Référence normative, PC/serveur |
| **K0-Lite** | INT32 Q16.16 | INT64 | Edge embarqué (Pi, Pico, microcontrôleurs) |

La présente spécification décrit les deux variantes. La **référence de conformance prioritaire** est K0-Full. K0-Lite est une variante conforme déclarée avec son propre vecteur de test.

---

## §3 — Représentation des valeurs

### K0-Full (INT64 Q32.32)
- Type natif : `int64_t` (C11 `<stdint.h>`) / `i64` (Rust) / `int` (Python, illimité)
- 1 bit signe, 31 bits partie entière, 32 bits partie fractionnaire
- Plage entière représentable : ±2³¹ − 1 unités
- Résolution : $2^{-32}$ ≈ 2.33 × 10⁻¹⁰

### K0-Lite (INT32 Q16.16)
- Type natif : `int32_t` / `i32`
- 1 bit signe, 15 bits partie entière, 16 bits partie fractionnaire
- Plage entière représentable : ±2¹⁵ − 1 unités
- Résolution : $2^{-16}$ ≈ 1.53 × 10⁻⁵

### Encodage canonique pour hashing
Tous les scalaires sont sérialisés en **little-endian** (8 octets pour K0-Full, 4 octets pour K0-Lite) avant ingestion dans le hash SHA-256.

---

## §4 — Opérations normatives

### §4.1 ADD_SAT — Addition avec saturation

**K0-Full :**
```
ax_add_sat(a, b) :
  s = (int128)a + (int128)b
  if s > INT64_MAX  → retourner INT64_MAX, lever AX_SATURATED
  if s < INT64_MIN  → retourner INT64_MIN, lever AX_SATURATED
  retourner (int64_t)s
```

**K0-Lite :**
```
add_sat(a, b) :
  s = (int64_t)a + (int64_t)b
  if s > INT32_MAX  → retourner INT32_MAX, lever AX_SATURATED
  if s < INT32_MIN  → retourner INT32_MIN, lever AX_SATURATED
  retourner (int32_t)s
```

**Propriété normative** : `ADD_SAT(a, b) = ADD_SAT(b, a)` (commutatif). Saturation sticky.

---

### §4.2 MUL_NORMATIVE — Multiplication avec arrondi RNE (ties-to-even)

**K0-Full :**
```
ax_mul_normative(a, b) :
  P = (int128)a × (int128)b          // produit exact Q64.64
  Q = P >> 32                         // candidat Q32.32, avant arrondi

  // Bits GRS extraits des 32 bits de garde (bits 31..0 de P)
  low_u32 = (uint32_t)(P & 0xFFFFFFFF)
  G = (low_u32 >> 31) & 1            // bit de garde (bit 31)
  R = (low_u32 >> 30) & 1            // bit d'arrondi (bit 30)
  S = (low_u32 & 0x3FFFFFFF) != 0    // sticky (bits 29..0)

  // Arrondi RNE (Round-to-Nearest-Even / ties-to-even)
  if G == 1 AND (R == 1 OR S == 1 OR (Q & 1) == 1) :
    Q = Q + 1

  // Flag AX_TRUNCATED si low_u32 != 0 (information perdue)
  if low_u32 != 0 :
    lever AX_TRUNCATED  // alias : AX_INEXACT (voir §5)

  // Saturation après arrondi
  retourner clamp_int64(Q)
```

**K0-Lite :**
```
mul_q(a, b) :
  P = (int64_t)a × (int64_t)b        // produit exact Q32.32
  Q = P >> 16                         // candidat Q16.16

  half = 1 << 15                      // 0x8000
  rem  = P & 0xFFFF                   // 16 bits basses

  // Arrondi RNE
  if rem > half :
    Q = Q + 1
  elif rem == half AND (Q & 1) == 1 :
    Q = Q + 1

  retourner clamp_int32(Q)
```

**Propriété normative** : `MUL_NORMATIVE(a, b) = MUL_NORMATIVE(b, a)` (commutatif, symétrique des bits GRS).

---

### §4.3 MAC — Multiply-Accumulate

```
ax_mac(a, b, acc) :
  prod = ax_mul_normative(a, b)       // avec flags
  retourner ax_add_sat(acc, prod)     // avec flags
```

L'ordre est fixé : multiplier d'abord, puis accumuler. Pas de fusion FMA. Ce choix garantit que le résultat est identique à `ADD_SAT(MUL_NORMATIVE(a,b), acc)`.

---

### §4.4 EMIT_O1 — Émission d'impulsions (fire-and-drain)

```
ax_emit_o1(x, theta, emit_cap) :
  // Préconditions normatives
  assert theta > 0        // sinon lever AX_DIV_ZERO, retourner x inchangé
  assert x >= 0           // sinon lever AX_INPUT_RANGE, retourner x inchangé

  // Nombre d'impulsions
  emit = (uint64_t)((int128)x / (int128)theta)  // division entière tronquée

  // Bornage du burst
  if emit > emit_cap :
    emit = emit_cap
    lever AX_BURST_CROP

  // Drain normative : x_new = x - emit × theta
  drain = ax_mul_normative(emit_as_q32(emit), theta)
  x_new = ax_add_sat(x, -drain)

  retourner (x_new, emit)
```

`emit_as_q32(n)` = `(int64_t)n << 32` (représente l'entier n en Q32.32).

---

### §4.5 LIF — Neurone Leaky Integrate-and-Fire K0

Le modèle LIF canonique K0 est défini par la séquence suivante, exécutée une fois par tick pour chaque neurone actif :

```
lif_step(v, inp, decay, bias, theta, refrac) :
  if refrac > 0 :
    refrac = refrac - 1
    retourner (v, spike=False, refrac)

  // Décroissance
  v = mul_normative(v, decay)            // decay ∈ [0, 1)
  // Entrée + biais
  v = add_sat(v, inp)
  v = add_sat(v, bias)
  // Bornage membranaire
  v = clamp(v, V_MIN, V_MAX)

  // Seuil
  if v >= theta :
    v = add_sat(v, -theta)              // drain
    v = clamp(v, V_MIN, V_MAX)
    retourner (v, spike=True, REFRAC_TICKS)

  retourner (v, spike=False, 0)
```

**Paramètres canoniques K0-Lite (réseau de test)**

| Paramètre | Valeur Q16.16 | Valeur physique |
|---|---|---|
| Q = 1 << 16 | 65536 | 1.0 |
| DECAY | 58982 | 0.9 (approx) |
| BIAS | 3276 | 0.05 |
| THETA (THR) | 65536 | 1.0 |
| V_MAX | 131072 | +2.0 |
| V_MIN | −131072 | −2.0 |
| REFRAC_TICKS | 3 | 3 |

---

## §5 — Flags d'anomalie (status)

Les flags sont des bits d'un entier non-signé 32 bits (`uint32_t`). Ils sont **sticky** : une fois levé, un flag reste levé sauf réinitialisation explicite.

| Flag | Bit | Alias normatif | Signification |
|---|---|---|---|
| `AX_SATURATED` | 0 | — | Saturation INT64/INT32 (overflow ADD ou MUL post-arrondi) |
| `AX_TRUNCATED` | 1 | `AX_INEXACT` | Information perdue après arrondi MUL_NORMATIVE |
| `AX_BURST_CROP` | 2 | — | Émission EMIT_O1 bornée par emit_cap |
| `AX_INPUT_RANGE` | 3 | — | Précondition EMIT_O1 violée (x < 0) |
| `AX_DIV_ZERO` | 4 | — | Précondition EMIT_O1 violée (theta ≤ 0) |

**Note normative** : `AX_TRUNCATED` et `AX_INEXACT` sont des alias. Les implémentations DOIVENT lever le bit 1 dans les deux cas. Les deux noms sont acceptés dans les interfaces, mais la valeur binaire (bit 1) est l'invariant.

---

## §6 — PRNG déterministe (splitmix64)

Le générateur pseudo-aléatoire utilisé dans les suites de test est **splitmix64** avec seed figé :

```c
uint64_t seed = 0xA10ULL + 0x123456789abcdef0ULL;  // = 0x123456789abce000

uint64_t splitmix64(uint64_t *x) {
    uint64_t z = (*x += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}
```

Ce PRNG est **spécifié** (invariant). Toute implémentation conforme doit reproduire la même séquence de nombres.

---

## §7 — Suite de test normative (vecteur de conformance)

### K0-Full (N = 200 000 itérations)

Pour chaque itération i de 0 à N-1 :
1. Générer `a`, `b`, `x`, `theta`, `cap` via splitmix64 (dans cet ordre).
2. `theta` = next_seed | 1 (forcé impair pour éviter zéro)
3. `cap` = (next_seed % 128) + 1
4. Calculer `r_add = ax_add_sat(a, b)`, `r_mul = ax_mul_normative(a, b)`, `(x2, emit) = ax_emit_o1(x, theta, cap)`.
5. Ingérer dans SHA-256 (little-endian) : 8 + 8 + 8 + 8 octets de résultats, puis 4 octets de status.

**Hash de référence K0-Full (normative)** : `45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d`  
*(certifié C-GCC-O2 x86-64 + Python 3.11 x86-64, 2026-06-07)*

### K0-Lite (N = 200 000 itérations LIF)

Le vecteur de conformance K0-Lite est la trajectoire LIF complète (v_mem, spikes) d'un réseau canonique N=64 neurones, seed=42, 200 000 ticks.  
**Hash de référence K0-Lite** : `à établir Phase 2`.

---

## §8 — Sérialisation canonique pour hashing

1. Tous les scalaires : **little-endian**. INT64 → 8 octets. INT32 → 4 octets. UINT32 → 4 octets.
2. Booléens : 1 octet (0x00 = False, 0x01 = True).
3. Listes : éléments contigus dans l'ordre d'index, sans séparateur.
4. État LIF complet : `[v_mem_0, …, v_mem_{N-1}, refrac_0, …, refrac_{N-1}]`

**Note normative endianness** : K0 est little-endian par spécification. L'implémentation
de référence C sérialise via `b[i]=(uint8_t)(v>>(8*i))` — sérialisation explicite,
pas un `memcpy` implicite sur la représentation mémoire de la machine. Cela garantit
la portabilité sur toute architecture (y compris big-endian : MIPS, PowerPC, s390x),
**à condition que l'implémentation utilise la sérialisation explicite**.

Sur un système big-endian utilisant `memcpy` naïf au lieu de la sérialisation
explicite, le hash serait différent : ce serait un bug d'implémentation, pas
une violation de la spec. La spec est l'oracle ; la sérialisation est normative.

---

## §9 — Invariants de comportement garanti

1. **Déterminisme** : pour le même état initial et la même séquence d'entrées, le résultat est identique bit-à-bit sur toute plateforme conforme.
2. **Saturation explicite** : aucune opération ne produit de résultat hors-plage silencieux. AX_SATURATED est levé.
3. **Arrondi normé** : MUL_NORMATIVE applique RNE (ties-to-even). Pas d'arrondi par troncature simple.
4. **Flags observables** : toute anomalie est capturée dans le registre de status. Aucune exception silencieuse.
5. **Pas de flottant dans le chemin normé** : les opérations normatives ne font appel à aucune instruction virgule flottante. Les conversions float↔K0 sont autorisées uniquement hors du chemin normé (initialisation, affichage).
6. **Commutatif** : ADD_SAT et MUL_NORMATIVE sont commutatifs.

---

## §10 — Ce que K0 ne revendique PAS

- K0 ne revendique PAS d'être plus efficace que le flottant IEEE-754.
- K0 ne revendique PAS d'être biologique ou neuralement réaliste.
- K0 ne revendique PAS que K0-Full et K0-Lite sont bit-exact entre elles.
- K0 ne revendique PAS d'être le premier SNN entier (L-SPINE, Loihi 2, Full Integer Training 2025 existent).
- K0 revendique **uniquement** : toute implémentation conforme à cette spec produit exactement le même hash sur n'importe quelle plateforme conforme.

---

## §11 — Historique des versions

| Version | Date | Changements |
|---|---|---|
| 1.0 | 2026-03 | Prototype initial, Q16.16, K0-Lite uniquement |
| 2.0 | 2026-05 | Ajout K0-Full Q32.32, MUL_NORMATIVE GRS formalisé |
| 2.5 | 2026-06-07 | FIGÉE. Alias AX_INEXACT≡AX_TRUNCATED documenté. Seed figé. Sérialisation canonique. Vecteur de test normé. |

---

## §12 — Licence

Cette spécification est publiée sous licence **CC BY 4.0** (Creative Commons Attribution 4.0).  
Les implémentations de référence (`ax.c`, `ax.h`, code Python/Rust conformes) sont publiées sous **AGPL-3.0-only**.
