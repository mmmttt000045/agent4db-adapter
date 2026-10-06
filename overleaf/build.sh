#!/usr/bin/env bash
# Compile the shared manuscript or package its sources for Overleaf.
# Usage: ./build.sh [en|bi|all|pack]   (default: all)
set -euo pipefail
cd "$(dirname "$0")"
target="${1:-all}"

case "$target" in
  en|bi|all|pack) ;;
  *) echo "usage: $0 [en|bi|all|pack]" >&2; exit 2 ;;
esac

if [ "$target" = pack ]; then
  python3 - <<'PY'
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

root = Path.cwd()
files = {
    Path('README.md'), Path('build.sh'), Path('acmart.cls'),
    Path('latex/acmart/acmart.dtx'),
}

def collect(path, stack=()):
    if path in stack:
        raise SystemExit(f'Circular input: {path}')
    if not (root / path).is_file():
        raise SystemExit(f'Missing source: {path}')
    if path in files:
        return
    files.add(path)
    source = (root / path).read_text(encoding='utf-8')
    for name in re.findall(r'\\input\{([^}]+)\}', source):
        child = Path(name if name.endswith('.tex') else name + '.tex')
        if child.is_absolute() or '..' in child.parts:
            raise SystemExit(f'Input outside the paper directory: {child}')
        collect(child, (*stack, path))
    for name in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', source):
        graphic = Path(name if Path(name).suffix else name + '.pdf')
        if graphic.is_absolute() or '..' in graphic.parts:
            raise SystemExit(f'Graphic outside the paper directory: {graphic}')
        if not (root / graphic).is_file():
            raise SystemExit(f'Missing graphic: {graphic}')
        files.add(graphic)

for entry in ('main.tex', 'main-en.tex'):
    collect(Path(entry))

archive = 'mavra-sigmod-bilingual.zip'
with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
    for path in sorted(files):
        info = ZipInfo(path.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_DEFLATED
        info.external_attr = (0o100755 if path.name == 'build.sh' else 0o100644) << 16
        bundle.writestr(info, (root / path).read_bytes())
print(f'{archive}: {len(files)} source files')
PY
  exit 0
fi

if command -v latexmk >/dev/null 2>&1; then
  engine=latexmk
elif command -v tectonic >/dev/null 2>&1; then
  engine=tectonic
else
  echo 'Install latexmk with pdfLaTeX/XeLaTeX, or Tectonic, to compile the paper.' >&2
  exit 1
fi

check_dependencies() {
  local dependency
  local -a required_files=(
    xkeyval.sty xstring.sty iftex.sty microtype.sty etoolbox.sty
    booktabs.sty refcount.sty totpages.sty environ.sty setspace.sty
    framed.sty zref-savepos.sty zref-user.sty natbib.sty babel.sty
    hyperref.sty hyperxmp.sty graphicx.sty xcolor.sty geometry.sty
    manyfoot.sty cmap.sty libertine.sty zi4.sty newtxmath.sty
    amssymb.sty pifont.sty caption.sty float.sty comment.sty
    fancyhdr.sty balance.sty amsmath.sty tabularx.sty
    colortbl.sty algorithm.sty algpseudocode.sty
  )
  local -a missing_files=()
  if [ "$target" != en ]; then
    required_files+=(
      ctex.sty xeCJK.sty fontspec.sty unicode-math.sty
      FandolSong-Regular.otf FandolHei-Regular.otf
      FandolFang-Regular.otf FandolKai-Regular.otf LinLibertine_R.otf
    )
  fi
  for dependency in "${required_files[@]}"; do
    if [ ! -f "$dependency" ] && ! kpsewhich "$dependency" >/dev/null 2>&1; then
      missing_files+=("$dependency")
    fi
  done
  if [ "${#missing_files[@]}" -gt 0 ]; then
    echo 'The TeX installation is missing these packages or fonts:' >&2
    printf '  %s\n' "${missing_files[@]}" >&2
    echo 'Install the dependencies in the compilation environment; see README.md.' >&2
    return 1
  fi
}

if [ "$engine" = latexmk ] && command -v kpsewhich >/dev/null 2>&1; then
  check_dependencies
fi

compile() {  # $1 = source, $2 = latexmk engine flag
  local source="$1" flag="$2" log="build/${1%.tex}.build.log"
  if [ "$engine" = latexmk ]; then
    latexmk "$flag" -interaction=nonstopmode -halt-on-error -outdir=build "$source" > "$log" 2>&1 \
      || { tail -40 "$log"; echo "FAILED: $source" >&2; return 1; }
  else
    tectonic --keep-logs --keep-intermediates --outdir build "$source" > "$log" 2>&1 \
      || { tail -40 "$log"; echo "FAILED: $source" >&2; return 1; }
  fi
  sed -nE 's/.*Output written on .*\(([0-9]+) pages?.*/'"$source"': \1 pages/p' "build/${source%.tex}.log"
  if command -v rg >/dev/null 2>&1; then
    rg '^(LaTeX|Package|Class) .*Warning' "build/${source%.tex}.log" | sort -u | head -20 || true
  fi
}

mkdir -p build
case "$target" in
  en)  compile main-en.tex -pdf ;;
  bi)  compile main.tex -xelatex ;;
  all) compile main-en.tex -pdf; compile main.tex -xelatex ;;
esac
