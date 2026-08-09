import pathlib, json, hashlib, sys

ROOT = pathlib.Path(r'.')
REF = '45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d'
checks = []

def chk(label, ok, detail=''):
    mark = '[OK]' if ok else '[!!]'
    checks.append((ok, label, detail))
    print('  ' + mark + ' ' + label + ('  -> ' + detail if detail else ''))

# 1. cargo k0_test binary
k0_test_exe = pathlib.Path(r'target/release/k0_test')
chk('cargo k0_test binary', k0_test_exe.exists(), str(k0_test_exe.name))

# 2. matrix_manifest 7 cells
mm = json.loads((ROOT / 'experiments/k0_cross_platform/results/matrix_manifest.json').read_text())
chk('matrix_manifest 7 cells', mm['n_cells'] == 7, 'n_cells=' + str(mm['n_cells']))
chk('matrix_manifest all_match', mm['all_match_reference'], 'sha=' + mm['manifest_sha256'][:16])

# 3. paper
paper = ROOT / 'paper/K0_paper_draft_v0.1.md'
ptext = paper.read_text(encoding='utf-8')
chk('paper draft exists', paper.exists(), paper.name)
chk('paper v1.0', 'Draft v1.0' in ptext, 'version tag')
chk('no fictitious committee', 'comite fictif' not in ptext.lower() and 'fictitious' not in ptext.lower())
chk('section 4.5 Rust bench', '4.5 Rust Implementation Benchmark' in ptext)
chk('section 4.6 NIR backend', '4.6 NIR-K0 Backend' in ptext)
chk('limitation CPython', 'CPython float is cross-platform' in ptext)
chk('limitation NIR 1.0.7', 'NIR 1.0.7 API limitation' in ptext)
chk('limitation Rust u128', 'Rust u128' in ptext or 'Rust `u128`' in ptext)
chk('SHA fix documented', 'corrupted assertion string' in ptext)
chk('ISA overhead note', 'ISA-dependent overhead note' in ptext)
chk('AX_TRUNCATED observability', 'AX_TRUNCATED observability' in ptext)

# 4. CITATION.cff
cff = ROOT / 'CITATION.cff'
ctext = cff.read_text(encoding='utf-8')
chk('CITATION.cff exists', cff.exists())
chk('CITATION author Denoual', 'Denoual' in ctext)
chk('CITATION license AGPL-3.0-only', 'AGPL-3.0-only' in ctext)

# 5. LICENSE
lic = ROOT / 'LICENSE'
ltext = lic.read_text() if lic.exists() else ''
chk('LICENSE AGPL-3.0-only', lic.exists() and 'GNU Affero General Public License' in ltext)

# 6. baseline_divergence results
bd = ROOT / 'experiments/baseline_divergence/results/results_amd64_quick.json'
if bd.exists():
    bj = json.loads(bd.read_text())
    chk('baseline_divergence results', bj.get('summary', {}).get('float_order_diverges'), 'diverge_tick=' + str(bj.get('float_ab_diverge_tick', '?')))
else:
    chk('baseline_divergence results', False, 'MISSING')

# 7. aarch64 results
ar = ROOT / 'experiments/k0_cross_platform/results/phase2a_aarch64_results.json'
chk('aarch64 results JSON', ar.exists())

# 8. Rust cell JSONs
chk('cell_rust_amd64.json', (ROOT/'experiments/k0_cross_platform/results/cell_rust_amd64.json').exists())
chk('cell_rust_aarch64.json', (ROOT/'experiments/k0_cross_platform/results/cell_rust_aarch64.json').exists())

# 9. CONFORMANCE.md
conf = ROOT / 'spec/CONFORMANCE.md'
cconf = conf.read_text(encoding='utf-8')
chk('CONFORMANCE Phase 2b Rust', 'Phase 2b' in cconf)
chk('CONFORMANCE manifest sha', '1b2035a9' in cconf)

# 10. Figure 3 results
f3 = ROOT / 'experiments/k0_cross_platform/results/figure3_results.json'
chk('figure3_results.json', f3.exists())

# 11. NIR backend
nir_back = ROOT / 'python/nir_k0/k0_backend.py'
chk('nir_k0/k0_backend.py', nir_back.exists())

# 12. test_nir_k0.py results
nir_res = ROOT / 'experiments/k0_cross_platform/results/nir_k0_test_results.json'
if nir_res.exists():
    nr = json.loads(nir_res.read_text())
    chk('NIR 10/10 PASS', nr.get('passed') == 10 and nr.get('failed') == 0, 'verdict=' + nr.get('verdict', '?'))
else:
    chk('NIR test results', False, 'MISSING')

print()
n_ok = sum(1 for ok, _, _ in checks if ok)
total = len(checks)
print('  ' + str(n_ok) + '/' + str(total) + ' OK')
if n_ok == total:
    print('  ALL CHECKS PASS -- arXiv v1 ready')
else:
    print('  BLOCKERS:')
    for ok, label, detail in checks:
        if not ok:
            print('    [!!] ' + label + ' ' + detail)
