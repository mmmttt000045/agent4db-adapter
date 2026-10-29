"""Cumulative and per-question cost for sequential agents on TPC-DS.

Lines show means across runs; capped error bars show the per-agent minimum
and maximum across runs. The per-question panel retains its logarithmic axis.
Data and the paper's numerical cross-checks are unchanged.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.lines import Line2D  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402

NAME = 'population'
W, H = style.TEXTWIDTH, 54.0
DATA = style.ROOT / 'exp/2026-10-12-population/population-stats.json'
METHODS = [('middle-alone', 'None', '^'), ('metric-private', 'Private', 'D'), ('metric-global-snap', 'Mavra', 'o')]
TEXT = {
    'en': {'y': ['Tokens (M)', 'Agent time (min)', 'Tokens per question (k)'],
           'x': ['Agents arrived', 'Agents arrived', 'Agent (arrival order)'],
           'panels': ['(a) Cumulative tokens', '(b) Cumulative time', '(c) Per-question tokens']},
    'zh': {'y': ['token（百万）', '智能体时间（分钟）', '每题 token（千）'],
           'x': ['已到来的智能体数', '已到来的智能体数', '智能体（到来顺序）'],
           'panels': ['(a) 累计 token', '(b) 累计时间', '(c) 每题 token']},
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
    data, _ = load()
    T = TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 3, gridspec_kw=dict(left=.065, right=.99, top=.86, bottom=.22, wspace=.40))
    methods = [m for m in METHODS if m[0] in data]
    linestyles = {'middle-alone': '--', 'metric-private': '-.', 'metric-global-snap': '-'}
    handles = [
        Line2D([], [], color=mplstyle.color(mode), marker=marker, mfc='white', mew=.6,
               linestyle=linestyles[mode], label=mplstyle.name(mode, lang))
        for mode, _, marker in methods
    ]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.53, 1.0),
               ncol=len(handles), handlelength=2.4, columnspacing=2.0)
    n = len(data['middle-alone']['tok'])
    xs = list(range(1, n + 1))
    for k, ax in enumerate(axes):
        for mode, _, marker in methods:
            d, color = data[mode], mplstyle.color(mode)
            ys = (d['tok'], d['s'], d['per'])[k]
            lo = [min(c[k][i] for c in d['curves']) for i in range(n)]
            hi = [max(c[k][i] for c in d['curves']) for i in range(n)]
            ax.errorbar(xs, ys, yerr=[[y - low for y, low in zip(ys, lo)],
                                     [high - y for high, y in zip(hi, ys)]],
                        fmt='none', ecolor=color, elinewidth=.4, capsize=1.2,
                        capthick=.4, alpha=.7, zorder=2)
            ax.plot(xs, ys, color=color, ls=linestyles[mode], marker=marker,
                    mfc='white', mew=.6, ms=2.8,
                    markevery=sorted({0, *range(3, n, 4), n - 1}), zorder=3)
        ax.set_ylabel(T['y'][k])
        ax.set_xlabel(T['x'][k])
        if k == 2:
            ax.set_yscale('log')
            ax.set_ylim(4, 200)
            ax.set_yticks([5, 10, 20, 50, 100])
            ax.set_yticklabels(['5', '10', '20', '50', '100'])
            ax.minorticks_off()
        else:
            ax.set_ylim(bottom=0)
        ax.set_xlim(.7, n + .3)
        ax.set_xticks([1, 4, 8, 12, 16] if n == 16 else xs[::max(1, n // 4)])
        ax.yaxis.grid(True)
        box = ax.get_position()
        fig.text((box.x0 + box.x1) / 2, .025, T['panels'][k],
                 ha='center', va='bottom', fontsize=mplstyle.TITLE)
    return fig

if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
