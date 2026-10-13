"""Figure: what a population of agents pays on one database, by memory design.

Two panels share the x axis, the number of agents that have arrived (1-16, in
arrival order): the left panel the total tokens of their sessions (including the
extraction tokens of the sessions the memory learned from), the right panel the
total agent-session time. For each method a line gives the mean over runs and a
light band spans the runs. The legend gives each method's accuracy on the
unchanged data. Data: exp/2026-10-12-population/population-stats.json (written
by tools/population-stats.py), checked against the \\Pp* macros the text prints.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.lines import Line2D  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import INK, MUTED, WHITE  # noqa: E402

NAME = 'population'
W, H = style.TEXTWIDTH, 50.0
DATA = style.ROOT / 'exp/2026-10-12-population/population-stats.json'
METHODS = [('middle-alone', 'None', '^'), ('metric-private', 'Private', 'D'), ('traj-global', 'Traj', 's'),
           ('metric-global-snap', 'Mavra', 'o')]
TEXT = {
    'en': {'panels': ['Total tokens (M)', 'Total agent time (min)', 'Tokens per question (k), by agent'],
           'x': 'Agents arrived', 'x3': 'Agent in arrival order',
           'acc': '{name} · {acc}% correct', 'save': '−{t}% tokens\n{s}× faster'},
    'zh': {'panels': ['累计 token（百万）', '累计智能体时间（分钟）', '每题 token（千），按智能体'],
           'x': '已到来的智能体数', 'x3': '按到来顺序的智能体',
           'acc': '{name} · 正确率 {acc}%', 'save': 'token 少 {t}%\n快 {s} 倍'},
}


def load():
    d = json.loads(DATA.read_text(encoding='utf-8'))['methods']
    pp = style.macros('population')
    out = {}
    for mode, key, _ in METHODS:
        if mode not in d:
            continue
        cells = d[mode]['cells']
        curves = []
        for c in cells:
            tok, s, per, ct, cs = [], [], [], 0.0, 0.0
            for a in c['per_agent']:
                ct += a['tok']
                cs += a['s']
                tok.append(ct / 1e6)
                s.append(cs / 60)
                per.append(a['tok'] / max(a['tasks'], 1) / 1e3)
            curves.append((tok, s, per))
        n = len(curves[0][0])
        mean_tok = [sum(c[0][i] for c in curves) / len(curves) for i in range(n)]
        mean_s = [sum(c[1][i] for c in curves) / len(curves) for i in range(n)]
        acc = d[mode]['v1']['acc']['mean'] * 100
        style.agree(f'Pp{key}TotalTokM', f'{mean_tok[-1]:.2f}', pp[f'Pp{key}TotalTokM'])
        style.agree(f'Pp{key}Acc', f'{acc:.0f}', pp[f'Pp{key}Acc'])
        mean_per = [sum(c[2][i] for c in curves) / len(curves) for i in range(n)]
        out[mode] = dict(curves=curves, tok=mean_tok, s=mean_s, per=mean_per, acc=f'{acc:.0f}')
    gain = (pp['PpMavraTokSaveNone'], pp['PpMavraSpeedupNone'])
    return out, gain


def figure(lang):
    data, (save, speed) = load()
    T = TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 3, gridspec_kw=dict(left=.045, right=.99, top=.74, bottom=.17, wspace=.22))
    handles = []
    methods = [m for m in METHODS if m[0] in data]
    for mode, _, marker in methods:
        label, color = style.method(mode, lang)
        handles.append(Line2D([], [], color=color, marker=marker, ms=3.4, mfc=color, mec=WHITE, mew=.35, lw=1.0,
                              label=T['acc'].format(name=label, acc=data[mode]['acc'])))
    legend = fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.52, 1.0), ncol=4, handlelength=1.6,
                        columnspacing=1.6)
    for entry in legend.get_texts():
        if entry.get_text().startswith('MAVRA'):
            entry.set_color(style.method('metric-global-snap', lang)[1])
            entry.set_fontweight('bold')
    n = len(data['middle-alone']['tok'])
    xs = list(range(1, n + 1))
    for k, ax in enumerate(axes):
        for mode, _, marker in methods:
            _, color = style.method(mode, lang)
            d = data[mode]
            ys = (d['tok'], d['s'], d['per'])[k]
            lo = [min(c[k][i] for c in d['curves']) for i in range(n)]
            hi = [max(c[k][i] for c in d['curves']) for i in range(n)]
            ax.fill_between(xs, lo, hi, color=color, alpha=.16, lw=0, zorder=1)
            ax.plot(xs, ys, color=color, lw=1.0, zorder=3)
            ax.plot(xs[3::4], ys[3::4], ls='', marker=marker, ms=3.0, mfc=color, mec=WHITE, mew=.35, zorder=4)
        ax.set_title(T['panels'][k], pad=3, loc='left')
        if k == 2:
            ax.set_yscale('log')
            ax.set_ylim(4, 200)
            ax.set_yticks([5, 10, 20, 50, 100])
            ax.set_yticklabels(['5', '10', '20', '50', '100'])
            ax.minorticks_off()
        ax.set_xlim(1, n)
        ax.set_xticks([1, 4, 8, 12, 16] if n == 16 else xs[::max(1, n // 4)])
        if k < 2:
            ax.set_ylim(0, None)
        ax.grid(True)
        ax.set_axisbelow(True)
    # The saving at the last agent, against exploring alone
    ax = axes[0]
    top, low = data['middle-alone']['tok'][-1], data['metric-global-snap']['tok'][-1]
    ax.annotate('', xy=(n - .4, low), xytext=(n - .4, top),
                arrowprops=dict(arrowstyle='-|>', color=MUTED, lw=.6, mutation_scale=5, shrinkA=0, shrinkB=0),
                zorder=5)
    # The note sits in the gap between the shared-memory lines and the next line above them, over the last agents
    tail = slice(n * 2 // 3, n)
    below = max(max(data[m]['tok'][tail]) for m in ('metric-global-snap', 'traj-global') if m in data)
    above = min(min(data[m]['tok'][tail]) for m in ('metric-private', 'middle-alone') if m in data)
    ax.text(n - .9, (below + above) / 2, T['save'].format(t=save, s=speed), ha='right', va='center',
            fontsize=mplstyle.SMALL, color=INK, linespacing=1.15)
    fig.text((.045 + .66) / 2, .02, T['x'], color=MUTED, fontsize=mplstyle.LABEL, ha='center', va='bottom')
    fig.text(.835, .02, T['x3'], color=MUTED, fontsize=mplstyle.LABEL, ha='center', va='bottom')
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
