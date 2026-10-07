"""Shared look, method names and data checks for the paper's figures.

Method colors are read from overleaf/latex/preamble.tex, the same
\\definecolor lines the tables' swatches use, so a figure can never show a
method in a different color than Table 2, whose names METHODS repeats. Figures that plot experiment data
read the archived JSON in exp/ and compare every number the text also prints
against the macros in overleaf/gen/; a mismatch stops the build.
"""
import re
from pathlib import Path

from vecfig import Sheet

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / 'overleaf'
OUT = PAPER / 'figures'

COLUMN, TEXTWIDTH = 84.6, 178.0        # acmart sigconf widths, mm


def _palette():
    text = (PAPER / 'latex/preamble.tex').read_text(encoding='utf-8')
    found = re.findall(r'\\definecolor\{(\w+)\}\{HTML\}\{([0-9A-Fa-f]{6})\}', text)
    return {name: '#' + value.upper() for name, value in found}


PAPER_COLORS = _palette()

# Drawing inks shared by all figures.
INK, MUTED, RULE = '#2B2A28', '#6B6A66', '#D3D0CA'
EDGE, FACE, SIDE, TOP = '#8E8B85', '#F6F5F2', '#DCD9D3', '#ECEAE5'
ACC, ACC_DK, ACC_PALE, FIELD = PAPER_COLORS['mCond'], '#1D5BA6', '#E3EEFB', '#F1F6FC'
SLATE, AMBER, AMBER_PALE = '#5E6E82', '#C98600', '#FBEFD3'
RED, WHITE = '#C2412E', '#FFFFFF'
ORANGE, ORANGE_PALE = PAPER_COLORS['mDef'], '#FCE8DF'
GRID = PAPER_COLORS['gridline']

# Experiment method key -> (English, Chinese, color name), as in Table 2.
METHODS = {
    'middle': ('No memory', '无记忆', 'mNoShare'),
    'traj-global': ('Example retrieval', '示例检索', 'mTraj'),
    'traj-verify': ('Example retrieval + self-verification', '示例检索 + 自行核验', 'mTrajVerify'),
    'metric-global-noguard': ('Never revalidated', '从不重验证', 'mUnguarded'),   # not in the paper
    'metric-global-schema': ('Invalidate on schema change', '模式变更时失效', 'mSchema'),
    'metric-global-revoke': ('Invalidate on every write', '每次写入即失效', 'mRevoke'),
    'metric-global-def': ('Full recheck per definition', '整定义重查', 'mDef'),
    'metric-global-snap': ('MAVRA', 'MAVRA', 'mCond'),
    'metric-global-exref': ('MAVRA, regression on current data', 'MAVRA，回归测试用当前数据', 'mCondCur'),
    'metric-global': ('MAVRA, gold-SQL reference', 'MAVRA，标准答案作参照', 'mCondGold'),
    'tabletest': ('dbt-style table tests', 'dbt 式表级测试', 'mTable'),
    'definition': ('Full recheck per definition', '整定义重查', 'mDef'),
    'definition-cache': ('Full recheck + query cache', '整定义重查 + 查询缓存', 'mCache'),
    'condition-scope': ('Recheck changed tables only', '只重查变化的表', 'mScope'),
    'condition': ('MAVRA', 'MAVRA', 'mCond'),
    'condition-current': ('MAVRA, regression on current data', 'MAVRA，回归测试用当前数据', 'mCondCur'),
}


def method(key, lang):
    en, zh, color = METHODS[key]
    return (en if lang == 'en' else zh), PAPER_COLORS[color]


def macros(name):
    """\\newcommand values of overleaf/gen/<name>.tex as strings."""
    text = (PAPER / 'gen' / f'{name}.tex').read_text(encoding='utf-8')
    return dict(re.findall(r'\\newcommand\{\\(\w+)\}\{((?:[^{}]|\{[^{}]*\})*)\}', text))


def agree(what, shown, printed):
    """Stop when a plotted value, formatted as the text prints it, differs."""
    if shown != printed:
        raise SystemExit(f'{what}: figure data gives {shown}, the paper prints {printed}')


def build(figure, out=OUT):
    """Write <name>.pdf and <name>-zh.pdf for a figure module.

    A module with figure(lang) is a matplotlib figure (see mplstyle.py); one
    with draw(sheet, lang) is drawn with the vecfig kit.
    """
    paths = []
    for lang, suffix in (('en', ''), ('zh', '-zh')):
        path = Path(out) / f'{figure.NAME}{suffix}.pdf'
        if hasattr(figure, 'figure'):
            import mplstyle
            mplstyle.setup(lang)
            mplstyle.save(figure.figure(lang), path)
        else:
            sheet = Sheet(path, figure.W, figure.H)
            figure.draw(sheet, lang)
            sheet.save()
        paths.append(path)
    return paths
