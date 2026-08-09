# Public Scope, License, and Citation

This repository is the public reproduction package for K0/ArithSpec conformance artifacts:

```text
https://github.com/Prev56/arithspec-k0-public-repro
```

The repository `Prev56/arithspec-ax-k0` is a private/internal working repository. It is not the public reproduction source and should not be used as the public citation target.

Ce dépôt contient uniquement les artefacts publics K0 nécessaires à la reproduction des résultats explicitement listés.

## What Is Public

Public artifacts in this repository:

- K0 normative specification and conformance criteria.
- C, Python, and Rust reference implementations for K0 conformance checks.
- Public experiment scripts and frozen public result files needed for reproduction.
- Public TLA+ models and TLC outputs included in this package.
- Public papers, figures, reports, and manifests included in this package.

Not included:

- Private project logic.
- Internal governance files.
- Private parameters, budgets, or orchestration scripts.
- Credentials, tokens, SSH runners, machine-specific paths, or private infrastructure details.

## License Map

| Component | License |
|---|---|
| Code in `csrc/`, `python/`, `rust/`, `ros2/`, and reproduction scripts | AGPL-3.0-only |
| Normative specification in `spec/` | CC BY 4.0 |
| Papers, figures, reports, experiment descriptions, and result files | CC BY 4.0 |
| Root `LICENSE` file | GNU Affero General Public License v3.0 text for the code components; SPDX identifier `AGPL-3.0-only` |

## Citation

For software/package citation, use `CITATION.cff` in this repository.

For the main ArithSpec paper, cite:

```text
Denoual, J.-R. (2026). A Normative Arithmetic Substrate for Bit-Exact Spiking Neural Networks. Eventcompute. https://doi.org/10.5281/zenodo.20723009
```

Concept DOI for all versions:

```text
https://doi.org/10.5281/zenodo.20723008
```

Additional public Zenodo records:

| Record | DOI |
|---|---|
| Record A, per-tick certification | https://doi.org/10.5281/zenodo.21749447 |
| Record B, margins and low precision | https://doi.org/10.5281/zenodo.21750037 |
| Record D, rate-level robustness | https://doi.org/10.5281/zenodo.21750043 |
| Record E, quantization invariance | https://doi.org/10.5281/zenodo.21750054 |
