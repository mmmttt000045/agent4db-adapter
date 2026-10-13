"""Figure: what 16 agents on one TPC-DS database pay with each memory, per agent or shared.

Three panels share the rows, one per method, grouped into no memory, memories
each agent keeps for itself (the paper's single-agent memory and the published
AWM, ACE, Mem0, and AgentSM), and memories all agents share (example retrieval,
ACE and AgentSM shared, MAVRA): total tokens of the 16 agents (including
learning), their total agent time, and the share of questions answered
correctly after the restatement. A dotted line marks MAVRA's value. Data:
exp/2026-10-12-population/population-stats.json (tools/population-stats.py),
checked against the \\Pp* macros the text prints.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import INK, MUTED  # noqa: E402

NAME = 'baselines'
W, H = style.TEXTWIDTH, 52.0
DATA = style.ROOT / 'exp/2026-10-12-population/population-stats.json'
KEY = {'middle-alone': 'None', 'metric-private': 'Private', 'traj-global': 'Traj', 'metric-global-snap': 'Mavra',
       'mem-awm': 'Awm', 'mem-ace': 'Ace', 'mem-mem0': 'Memzero', 'mem-agentsm': 'Agentsm',
       'mem-ace-shared': 'AceShared', 'mem-agentsm-shared': 'AgentsmShared'}
GROUPS = [(None, ['middle-alone']),
          ('per', ['metric-private', 'mem-awm', 'mem-ace', 'mem-mem0', 'mem-agentsm']),
          ('shared', ['traj-global', 'mem-ace-shared', 'mem-agentsm-shared', 'metric-global-snap'])]
TEXT = {
    'en': {'panels': ['Total tokens of 16 agents (M)', 'Total agent time (min)', 'Correct after the restatement (%)'],
           'per': 'Each agent its own memory', 'shared': 'One memory for all agents'},
    'zh': {'panels': ['16 个智能体的累计 token（百万）', '累计智能体时间（分钟）', '更正之后的正确率（%）'],
           'per': '每个智能体各自的记忆', 'shared': '所有智能体共享一份记忆'},
}
REF = 'metric-global-snap'


def load():
    d = json.loads(DATA.read_text(encoding='utf-8'))['methods']
    pp = style.macros('population')
    out = {}
    for _, modes in GROUPS:
        for mode in modes:
            if mode not in d:
                continue
            r = d[mode]
            last = str(max(int(n) for n in r['cum']))
            tok = r['cum'][last]['tok']['mean'] / 1e6
            s = r['cum'][last]['s']['mean'] / 60
            ch = r['change']['acc']['mean'] * 100 if r['change']['acc'] else None
            style.agree(f'Pp{KEY[mode]}TotalTokM', f'{tok:.2f}', pp[f'Pp{KEY[mode]}TotalTokM'])
            if ch is not None:
                style.agree(f'Pp{KEY[mode]}ChangeAcc', f'{ch:.0f}', pp[f'Pp{KEY[mode]}ChangeAcc'])
            out[mode] = (tok, s, ch)
    return out


def rows(data, T):
    """(y, label, mode or None for a group header), top to bottom."""
    out, y = [], 0.0
    for group, modes in GROUPS:
        modes = [m for m in modes if m in data]
        if not modes:
            continue
        if group:
            y += .35
            out.append((y, T[group], None))
            y += .85
        for m in modes:
            out.append((y, None, m))
            y += 1
    return out


def figure(lang):
    data, T = load(), TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 3, sharey=True, gridspec_kw=dict(left=.105, right=.985, top=.90, bottom=.11, wspace=.08))
    layout = rows(data, T)
    for k, ax in enumerate(axes):
        vals = [data[m][k] for _, _, m in layout if m and data[m][k] is not None]
        top = max(vals) * 1.22 if k < 2 else 118
        for y, _, m in layout:
            if m is None or data[m][k] is None:
                continue
            v = data[m][k]
            _, color = style.method(m, lang)
            mine = m == REF
            ax.barh(y, v, height=.68, color=color, lw=0, zorder=3)
            text = f'{v:.2f}' if k == 0 else f'{v:.0f}'
            ax.text(v + top * .012, y, text, va='center', ha='left', fontsize=mplstyle.SMALL,
                    color=color if mine else INK, fontweight='bold' if mine else 'normal', zorder=4,
                    bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='none'))
        if REF in data and data[REF][k] is not None:
            ax.axvline(data[REF][k], color=style.method(REF, lang)[1], lw=.6, ls=(0, (1.0, 1.4)), zorder=2)
        ax.set_xlim(0, top)
        ax.set_title(T['panels'][k], pad=3, loc='left')
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.tick_params(axis='y', length=0)
        ax.spines['left'].set_visible(k == 0)
    ax = axes[0]
    ax.set_ylim(layout[-1][0] + .6, -.6)
    ax.set_yticks([y for y, _, _ in layout])
    ax.set_yticklabels(['' if m is None else style.method(m, lang)[0] for _, _, m in layout])
    # group headers sit in their own row, over the bars of the first panel
    for y, label, m in layout:
        if m is None:
            ax.text(0, y + .1, label, color=MUTED, fontsize=mplstyle.LABEL, fontstyle='italic', ha='left', va='center',
                    bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='none'), zorder=4)
    for tick, (_, _, m) in zip(ax.get_yticklabels(), layout):
        if m == REF:
            tick.set_color(style.method(REF, lang)[1])
            tick.set_fontweight('bold')
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
