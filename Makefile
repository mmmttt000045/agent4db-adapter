.DEFAULT_GOAL := help
PYTHON ?= python3
NPM ?= npm

.PHONY: help check index index-check paper paper-en paper-bi paper-pack figures deck-figures slides-deps slides

help:
	@printf '%s\n' \
	  'check         Rust format, tests, Clippy, and experiment index' \
	  'index         Regenerate exp/README.md from exp/catalog.json' \
	  'index-check   Check experiment coverage and local references' \
	  'paper         Build English and bilingual PDFs' \
	  'paper-en      Build the English PDF' \
	  'paper-bi      Build the bilingual PDF' \
	  'paper-pack    Package Overleaf sources (no TeX required)' \
	  'figures       Regenerate paper PDFs (drawing dependencies required)' \
	  'deck-figures  Regenerate deck PDFs and PNGs (also requires pdftoppm)' \
	  'slides-deps   Install locked PPT dependencies' \
	  'slides        Build PPT from existing PNGs into slides/build/'

check: index-check
	cargo fmt --check
	cargo test --locked
	cargo clippy --locked --all-targets -- -D warnings

index:
	$(PYTHON) tools/experiment-index.py

index-check:
	$(PYTHON) tools/experiment-index.py --check

paper:
	bash overleaf/build.sh all

paper-en:
	bash overleaf/build.sh en

paper-bi:
	bash overleaf/build.sh bi

paper-pack:
	bash overleaf/build.sh pack

figures:
	$(PYTHON) tools/figures/build.py
	$(PYTHON) tools/figures/population.py
	$(PYTHON) tools/figures/relbench_cumulative.py
	$(PYTHON) tools/figures/mechanism.py

deck-figures:
	$(PYTHON) tools/figures/build.py --deck
	@set -e; for f in slides/figures/*.pdf; do pdftoppm -r 300 -png -singlefile "$$f" "$${f%.pdf}"; done

slides-deps:
	$(NPM) --prefix slides ci

slides:
	$(NPM) --prefix slides run build
