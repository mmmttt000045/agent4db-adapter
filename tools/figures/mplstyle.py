"""Conventional, print-oriented matplotlib style for the paper's data figures.

Use serif text, black axes, equal method weights, and embedded TrueType fonts.
Method colours still come from preamble.tex; markers, dashes, and bar hatches
make comparisons readable without relying on colour. Schematics keep the
separate ReportLab renderer in vecfig.py.
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import colors, font_manager, pyplot as plt  # noqa: E402

import style  # noqa: E402

MM = 1 / 25.4
LABEL, TICK, TITLE, SMALL = 7.5, 7.0, 8.0, 6.5
INK = '#000000'


def _families(lang):
    """Prefer installed Times/SimSun fonts, with portable serif fallbacks."""
    available = {font.name for font in font_manager.fontManager.ttflist}
    latin = next(name for name in ('Times New Roman', 'Liberation Serif', 'DejaVu Serif')
                 if name in available)
    family = [latin]
    if lang == 'zh':
        candidates = ('SimSun', 'Noto Serif CJK SC', 'Source Han Serif SC', 'FandolSong',
                      'Microsoft YaHei', 'Noto Sans CJK SC')
        cjk = next((name for name in candidates if name in available), None)
        if cjk is None:
            raise SystemExit('Chinese figures require SimSun or an installed Noto CJK font')
        family.append(cjk)
    return family


def setup(lang):
    """Set ordinary publication-style axes before creating a figure."""
    plt.rcdefaults()
    plt.rcParams.update({
        'font.family': _families(lang), 'font.size': LABEL,
        'mathtext.fontset': 'stix',
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'pdf.compression': 6,
        'figure.facecolor': 'white', 'axes.facecolor': 'white',
        'text.color': INK,
        'axes.linewidth': .6, 'axes.edgecolor': INK, 'axes.labelcolor': INK,
        'axes.labelsize': LABEL, 'axes.labelpad': 2,
        'axes.titlesize': TITLE, 'axes.titleweight': 'normal', 'axes.titlecolor': INK,
        'axes.spines.top': True, 'axes.spines.right': True,
        'axes.axisbelow': True,
        'xtick.color': INK, 'ytick.color': INK,
        'xtick.labelsize': TICK, 'ytick.labelsize': TICK,
        'xtick.direction': 'in', 'ytick.direction': 'in',
        'xtick.major.width': .5, 'ytick.major.width': .5,
        'xtick.major.size': 2.2, 'ytick.major.size': 2.2,
        'xtick.major.pad': 2, 'ytick.major.pad': 2,
        'grid.color': '#D0D0D0', 'grid.linewidth': .35, 'grid.linestyle': ':',
        'legend.frameon': False, 'legend.fontsize': LABEL,
        'legend.labelcolor': INK, 'legend.handletextpad': .4,
        'legend.columnspacing': 1.1, 'legend.borderaxespad': 0,
        'lines.linewidth': .9, 'lines.markersize': 3.2,
        'hatch.linewidth': .4, 'savefig.dpi': 300,
    })


def figure(w_mm, h_mm):
    return plt.figure(figsize=(w_mm * MM, h_mm * MM))


def save(fig, path):
    """Save vector marks and embedded text at the specified print size."""
    path = Path(path)
    fig.savefig(path, format='pdf', facecolor='white')
    plt.close(fig)
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f'{path}: matplotlib produced no output')


def bar_style(key, hatch):
    """Pale method fill with a black outline and a redundant hatch pattern."""
    rgb = colors.to_rgb(color(key))
    fill = tuple(.35 * channel + .65 for channel in rgb)
    return dict(facecolor=fill, edgecolor=INK, linewidth=.5, hatch=hatch)


def label_with_mark(ax, x, y, label, mark, transform, size=LABEL, color=INK, mark_width=.013):
    """Right-aligned label followed by a raised footnote mark (no CJK mathtext)."""
    if not mark:
        ax.text(x, y, label, transform=transform, ha='right', va='center', fontsize=size,
                color=color, clip_on=False)
        return
    ax.text(x - mark_width, y, label, transform=transform, ha='right', va='center',
            fontsize=size, color=color, clip_on=False, linespacing=.95)
    drop = label.count('\n') * size * .95 / 2
    ax.annotate(mark, (x - mark_width, y), xycoords=transform, xytext=(.3, 1.6 - drop),
                textcoords='offset points', ha='left', va='center', fontsize=size * .72,
                color=color, annotation_clip=False)


def color(key):
    return style.PAPER_COLORS[style.METHODS[key][2]]


def name(key, lang):
    return style.method(key, lang)[0]
