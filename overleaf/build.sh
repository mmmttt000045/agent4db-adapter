#!/usr/bin/env bash
# Export the English manuscript, compile both PDFs into build/, and report page counts.
# Usage: ./build.sh [en|bi|all]   (default: all)
set -euo pipefail
cd "$(dirname "$0")"
target="${1:-all}"

./export-english.sh

compile() {  # $1 = source, $2 = latexmk engine flag
  latexmk "$2" -interaction=nonstopmode -halt-on-error -outdir=build "$1" > "build/${1%.tex}.latexmk.log" 2>&1 \
    || { tail -40 "build/${1%.tex}.log"; echo "FAILED: $1" >&2; return 1; }
  grep -oE 'Output written on .*\([0-9]+ pages?' "build/${1%.tex}.log" | sed 's/.*(/'"$1"': /'
  grep -E '^(LaTeX|Package) .*Warning' "build/${1%.tex}.log" | grep -vE 'Font shape|substituted' | sort -u | head -20 || true
}

mkdir -p build
case "$target" in
  en)  compile main-en.tex -pdf ;;
  bi)  compile main.tex -xelatex ;;
  all) compile main-en.tex -pdf; compile main.tex -xelatex ;;
  *)   echo "unknown target: $target" >&2; exit 2 ;;
esac
