"""Shared matplotlib setup for the paper's data figures.

The data figures (replay outcomes, maintenance cost, scenario accuracy) are
drawn with matplotlib; the architecture diagram keeps the ReportLab kit in
vecfig.py. Both use the method colors of overleaf/latex/preamble.tex through
style.py, the same fonts as the paper (Linux Biolinum for labels, from TeX
Live; FandolHei for Chinese labels), and the same font floor (6 pt labels and
ticks, 7 pt titles). The PDF matplotlib writes embeds the OpenType fonts in a
form some PDF tools flag, so save() runs Ghostscript with -dNoOutputFonts and
the published figure contains outlines only, as the vecfig figures do.
Chinese labels must not go through mathtext (its fonts have no CJK glyphs);
footnote marks are drawn as separate raised text, see mark().
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager, pyplot as plt  # noqa: E402

import style  # noqa: E402
from style import GRID, INK, MUTED  # noqa: E402

MM = 1 / 25.4                      # inches per millimetre
LABEL, TICK, TITLE, SMALL = 6.5, 6.0, 7.0, 5.8   # pt
LATIN, CJK = 'Linux Biolinum O', 'FandolHei'
_registered = set()


def _kpsewhich(name):
    try:
        out = subprocess.run(['kpsewhich', name], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out) if out else None


def _register(lang):
    """Add the paper's fonts to matplotlib once per process."""
    if lang in _registered:
        return
    files = []
    biolinum = _kpsewhich('LinBiolinum_R.otf')
    if biolinum is None:
        raise SystemExit('LinBiolinum_R.otf not found; TeX Live with the libertine package is required')
    files += sorted(biolinum.parent.glob('LinBiolinum_*.otf'))
    if lang == 'zh':
        hei = _kpsewhich('FandolHei-Regular.otf')
        if hei is None:
            raise SystemExit('FandolHei-Regular.otf not found; TeX Live with the fandol package is required')
        files += sorted(hei.parent.glob('FandolHei-*.otf'))
    for f in files:
        font_manager.fontManager.addfont(str(f))
    names = {f.name for f in font_manager.fontManager.ttflist}
    for needed in [LATIN] + ([CJK] if lang == 'zh' else []):
        if needed not in names:
            raise SystemExit(f'font family {needed!r} not registered; found {sorted(n for n in names if "Bio" in n or "Fandol" in n)}')
    _registered.add(lang)


def setup(lang):
    """rcParams for one language; call before creating a figure."""
    _register(lang)
    family = [LATIN] + ([CJK] if lang == 'zh' else [])
    plt.rcdefaults()
    plt.rcParams.update({
        'font.family': family, 'font.size': LABEL,
        'mathtext.fontset': 'custom', 'mathtext.rm': LATIN, 'mathtext.it': f'{LATIN}:italic',
        'mathtext.bf': f'{LATIN}:bold',
        # Type 3 glyph outlines in the intermediate PDF: Ghostscript then turns every glyph into a
        # path, and the OpenType CFF fonts never have to be embedded as Type 42.
        'pdf.fonttype': 3, 'pdf.compression': 6,
        'axes.linewidth': .4, 'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'axes.labelsize': LABEL,
        'axes.titlesize': TITLE, 'axes.titleweight': 'bold', 'axes.titlecolor': INK,
        'axes.spines.top': False, 'axes.spines.right': False,
        'xtick.color': MUTED, 'ytick.color': MUTED, 'xtick.labelcolor': INK, 'ytick.labelcolor': INK,
        'xtick.labelsize': TICK, 'ytick.labelsize': TICK,
        'xtick.major.width': .4, 'ytick.major.width': .4, 'xtick.major.size': 1.8, 'ytick.major.size': 1.8,
        'xtick.major.pad': 2, 'ytick.major.pad': 2,
        'grid.color': GRID, 'grid.linewidth': .4,
        'legend.frameon': False, 'legend.fontsize': LABEL, 'legend.handletextpad': .4,
        'legend.columnspacing': 1.2, 'legend.borderaxespad': 0,
        'lines.linewidth': .9, 'lines.markersize': 3.6,
        'savefig.dpi': 300,
    })


def figure(w_mm, h_mm):
    return plt.figure(figsize=(w_mm * MM, h_mm * MM))


def save(fig, path):
    """Write the figure as a PDF of outlines only, then close it."""
    path = Path(path)
    gs = shutil.which('gs')
    if gs is None:
        raise SystemExit('Ghostscript (gs) is required to outline the figure text')
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / 'raw.pdf'
        fig.savefig(raw, format='pdf')
        subprocess.run([gs, '-q', '-o', str(path), '-sDEVICE=pdfwrite', '-dNoOutputFonts',
                        '-dCompatibilityLevel=1.5', str(raw)], check=True)
    plt.close(fig)
    if not path.exists() or os.path.getsize(path) == 0:
        raise SystemExit(f'{path}: Ghostscript produced no output')


def label_with_mark(ax, x, y, label, mark, transform, size=LABEL, color=INK, mark_width=.013):
    """Right-aligned label ending at x, followed by a raised footnote mark (no mathtext)."""
    if not mark:
        ax.text(x, y, label, transform=transform, ha='right', va='center', fontsize=size, color=color,
                clip_on=False)
        return
    ax.text(x - mark_width, y, label, transform=transform, ha='right', va='center', fontsize=size,
            color=color, clip_on=False, linespacing=.95)
    # The mark sits after the last line of a multi-line label.
    drop = label.count('\n') * size * .95 / 2
    ax.annotate(mark, (x - mark_width, y), xycoords=transform, xytext=(0.3, 1.6 - drop),
                textcoords='offset points', ha='left', va='center', fontsize=size * .72, color=color,
                annotation_clip=False)


def color(key):
    return style.PAPER_COLORS[style.METHODS[key][2]]


def name(key, lang):
    return style.method(key, lang)[0]
