"""Shared look, method names and data checks for the paper's figures.

Method colors are read from overleaf/latex/preamble.tex, the same
\\definecolor lines the tables' swatches use, so a figure can never show a
method in a different color than Table 3. Figures that plot experiment data
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

# Experiment method key -> (English, Chinese, color name), as in Table 3.
METHODS = {
    'middle': ('No sharing', '不共享', 'mNoShare'),
    'traj-global': ('Trajectory retrieval', '轨迹检索', 'mTraj'),
    'traj-verify': ('Trajectory + self-check', '轨迹检索 + 自检', 'mTrajVerify'),
    'metric-global-noguard': ('No validation', '共享不验证', 'mUnguarded'),
    'metric-global-schema': ('Schema-change invalidation', '按模式变更失效', 'mSchema'),
    'metric-global-revoke': ('Invalidate-on-write', '写入即失效', 'mRevoke'),
    'metric-global-def': ('Definition-level', '定义级', 'mDef'),
    'metric-global-snap': ('MAVRA', 'MAVRA', 'mCond'),
    'metric-global-exref': ('MAVRA, G8 on current data', 'MAVRA，G8 用当前数据', 'mCondCur'),
    'metric-global': ('MAVRA (gold SQL)', 'MAVRA（标准答案 SQL）', 'mCondGold'),
    'tabletest': ('Table tests', '表级测试', 'mTable'),
    'definition': ('Definition-level', '定义级', 'mDef'),
    'definition-cache': ('Check-result cache', '检查结果缓存', 'mCache'),
    'condition-scope': ('Affected-only', '只查受影响条件', 'mScope'),
    'condition': ('MAVRA', 'MAVRA', 'mCond'),
    'condition-current': ('MAVRA, G8 on current data', 'MAVRA，G8 用当前数据', 'mCondCur'),
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
    """Write <name>.pdf and <name>-zh.pdf for a figure module."""
    paths = []
    for lang, suffix in (('en', ''), ('zh', '-zh')):
        path = Path(out) / f'{figure.NAME}{suffix}.pdf'
        sheet = Sheet(path, figure.W, figure.H)
        figure.draw(sheet, lang)
        sheet.save()
        paths.append(path)
    return paths
