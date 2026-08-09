# Makefile K0 deterministic-snn
# Utilisation : make [target]
# Plateformes testées : Linux x86-64, Windows MinGW-W64, macOS arm64

CC      ?= gcc
CFLAGS  ?= -O2 -std=c11 -Wall -Wextra
PYTHON  ?= python3

.PHONY: all test-c test-python test-divergence test-all reproduce clean help

all: help

# ─── Reproduction complète (figures + hashes + checklist) ────────────────────
REF_K0FULL = 45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d

# Force Python UTF-8 mode so emoji status glyphs (OK/X) never crash on cp1252 consoles.
# Target-specific export works regardless of the recipe shell (cmd.exe or sh).
reproduce: export PYTHONUTF8 = 1
reproduce: export PYTHONIOENCODING = utf-8
reproduce: csrc/k0_test
	@echo "=========================================================="
	@echo " K0 — REPRODUCTION COMPLETE (hashes + figures + checklist)"
	@echo "=========================================================="
	@echo "--- [1/6] C K0-Full (gcc) ---"
	@./csrc/k0_test
	@echo "--- [2/6] Python K0-Full ---"
	@$(PYTHON) python/k0_full_test.py
	@echo "--- [3/6] Baseline divergence (float vs K0) ---"
	@$(PYTHON) experiments/baseline_divergence/baseline_divergence.py --mode quick
	@echo "--- [4/6] Figure 3 (NIR float vs K0) ---"
	@$(PYTHON) experiments/figure3_nir_float_vs_k0.py || echo "  (figure3 script optional)"
	@echo "--- [5/6] NIR-K0 backend test suite ---"
	@$(PYTHON) experiments/test_nir_k0.py || echo "  (nir test optional)"
	@echo "--- [6/6] arXiv checklist ---"
	@$(PYTHON) experiments/arxiv_checklist.py
	@echo "=========================================================="
	@echo " Reference K0-Full N=200000: $(REF_K0FULL)"
	@echo " Reproduction complete. Compare the printed hashes above."
	@echo "=========================================================="

# ─── Compilation C ───────────────────────────────────────────────────────────

csrc/k0_test: csrc/ax.c csrc/ax.h csrc/ax_k0_test.c
	$(CC) $(CFLAGS) csrc/ax.c csrc/ax_k0_test.c -o csrc/k0_test

# ─── Tests ───────────────────────────────────────────────────────────────────

test-c: csrc/k0_test
	@echo "=== Test conformance K0-Full (C) ==="
	./csrc/k0_test
	@echo "Attendu: AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d"

test-python:
	@echo "=== Test conformance K0-Full (Python) ==="
	$(PYTHON) python/k0_full_test.py
	@echo "Attendu: AX_K0_TEST_SHA256=45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d"

test-divergence:
	@echo "=== Expérience divergence baseline (quick) ==="
	$(PYTHON) experiments/baseline_divergence/baseline_divergence.py --mode quick

test-divergence-full:
	@echo "=== Expérience divergence baseline (full, 10k ticks) ==="
	$(PYTHON) experiments/baseline_divergence/baseline_divergence.py --mode full

test-all: test-c test-python test-divergence
	@echo ""
	@echo "=== TOUS LES TESTS PASSÉS ==="

# ─── Comparaison cross-platform ──────────────────────────────────────────────

compare-results:
	@if [ -z "$(FILE1)" ] || [ -z "$(FILE2)" ]; then \
		echo "Usage: make compare-results FILE1=results/x86.json FILE2=results/arm.json"; \
		exit 1; \
	fi
	$(PYTHON) experiments/baseline_divergence/baseline_divergence.py \
		--mode compare --file1 $(FILE1) --file2 $(FILE2)

# ─── Nettoyage ───────────────────────────────────────────────────────────────

clean:
	rm -f csrc/k0_test csrc/k0_test.exe csrc/k0_debug csrc/k0_debug.exe

# ─── Aide ────────────────────────────────────────────────────────────────────

help:
	@echo "K0 deterministic-snn — Cibles disponibles :"
	@echo ""
	@echo "  make test-c              Compile et teste C (GCC -O2)"
	@echo "  make test-python         Teste Python (k0_full_test.py)"
	@echo "  make test-divergence     Exp. divergence float vs K0 (quick)"
	@echo "  make test-divergence-full Exp. divergence (full, 10k ticks)"
	@echo "  make test-all            Tous les tests"
	@echo ""
	@echo "  make compare-results FILE1=... FILE2=..."
	@echo "                           Compare résultats cross-platform"
	@echo ""
	@echo "  make clean               Supprimer les binaires"
	@echo ""
	@echo "Hash de référence attendu (K0-Full, N=200000) :"
	@echo "  45ff9803bb5254fb04af2ec70c865ec981f3f6d221894c3acb769bc2847f000d"
