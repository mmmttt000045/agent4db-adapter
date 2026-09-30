#!/usr/bin/env bash
# Linux counterpart of export-english.ps1: regenerate main-en.tex from main.tex.
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(grep -cE '^\\bilingualtrue[[:space:]]*$' main.tex)" -ne 1 ]; then
  echo 'Expected exactly one bilingual switch in main.tex.' >&2
  exit 1
fi
sed -E -e 's/^\\bilingualtrue[[:space:]]*$/\\bilingualfalse/' \
       -e 's/% !TeX program = xelatex/% !TeX program = pdflatex/' main.tex \
  | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}' > main-en.tex
echo 'Updated main-en.tex from main.tex.'
