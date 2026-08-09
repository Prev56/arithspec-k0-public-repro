# K0 — Deterministic SNN: public reproduction package

Bit-exact, cross-platform integer arithmetic substrate for spiking neural networks.
This package lets anyone **reproduce the public conformance hashes** independently.
The canonical public repository is:

```text
https://github.com/Prev56/arithspec-k0-public-repro
```

Ce dépôt contient uniquement les artefacts publics K0 nécessaires à la reproduction des résultats explicitement listés.

The repository `Prev56/arithspec-ax-k0` is private/internal and is not the public reproduction source.

## Reference hashes

| Variant | SHA-256 (N=200000) |
|---|---|
| K0-Full (INT64 / Q32.32) | `45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d` |
| K0-Lite (INT32 / Q16.16) | `e1606bef1b34afe155adeace4aae7fd2aa22f0236ada22a61dd71631baae050a` |

## Quick reproduction

```bash
# C reference
cd csrc && gcc -O2 -std=c11 ax.c ax_k0_test.c -o k0_test && ./k0_test
# Python reference
python python/k0_full_test.py
# Rust reference
cd rust && cargo run --bin k0_test --release
# One-shot (hashes + figures + checklist)
make reproduce
```

Each prints `AX_K0_TEST_SHA256=45ff9803...`. Any K0-conformant implementation, on any
platform with 64-bit two's-complement integers and 128-bit multiply, must produce the same hash.

## Contents

- `csrc/` — C reference (K0-Full INT64, GRS+RNE, 5 status flags) + benchmark.
- `python/` — Python reference + NIR→K0 backend (`nir_k0/`).
- `rust/` — Rust reference (K0-Full + K0-Lite, zero external deps).
- `formal/` — TLA+ composition spec + TLC model-check output (5 invariants, 19,683 states).
- `ros2/` — ROS 2 K0-Lite controller node + standalone determinism test.
- `spec/` — normative spec v2.5 + conformance criteria.
- `experiments/` — divergence, cost, cross-platform matrix, NIR, Figure 3, checklist.
- `paper/` — preprint draft v1.0.

## Scope / boundary

This is the **public K0 substrate** only. It is limited to the public artifacts required for the explicitly listed K0 reproduction results.
Multi-platform orchestration scripts (remote SSH runners) are **intentionally excluded** —
reproduction here is fully local and needs only a C compiler, Python, and optionally Rust.

## License

Code is AGPL-3.0-only licensed. Specification, papers, reports, figures, experiments, and result files are CC BY 4.0 unless a file says otherwise. Cite via `CITATION.cff` and see `PUBLIC_SCOPE_AND_CITATION.md` for the full license/citation map.
