"""Figure: what a consumer pays per held-out question, on two schemas.

Two panels share both axes: the synthetic retail fixture (five runs per method)
and TPC-H SF1 (three runs per method). x is the mean agent-session time per
held-out question, y the mean tokens (input + output) per question. Small
hollow markers are single runs; the large filled marker pools all questions of
a method (the definition of tools/sharing-stats.py). A grey arrow runs from
exploring alone to MAVRA and carries the pooled speedup and token saving.
Data: exp/2026-10-10-scenarios-q5/holdout-cost.json (per-run sums, computed
from the cells of results/scen-20261010) and exp/2026-10-11-generality/e2e/
outcomes.json.gz, checked against the \\Am* and \\Ge* macros the text prints.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.lines import Line2D  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import INK, MUTED, WHITE  # noqa: E402

NAME = 'consumer-cost'
W, H = style.COLUMN, 42.0
SYN = style.ROOT / 'exp/2026-10-10-scenarios-q5/holdout-cost.json'
TPCH = style.ROOT / 'exp/2026-10-11-generality/e2e/outcomes.json.gz'
METHODS = [('middle', '^'), ('traj-global', 's'), ('metric-global-snap', 'o')]
TEXT = {
    'en': {'panels': ['Synthetic retail, {runs} runs', 'TPC-H SF1, {runs} runs'],
           'x': 'Seconds per held-out question', 'y': 'k tokens per question',
           'gain': '{s}× faster\n{t}% fewer tokens'},
    'zh': {'panels': ['合成零售数据，{runs} 次运行', 'TPC-H SF1，{runs} 次运行'],
           'x': '每道留出题的秒数', 'y': '每题 token（千）',
           'gain': '快 {s} 倍\ntoken 少 {t}%'},
}


def synthetic():
    d = json.loads(SYN.read_text(encoding='utf-8'))['methods']
    out = {}
    for mode, _ in METHODS:
        runs = d[mode]
        per = [(r['s_sum'] / r['n'], r['tok_sum'] / r['n'] / 1000) for r in runs]
        n = sum(r['n'] for r in runs)
        out[mode] = (per, (sum(r['s_sum'] for r in runs) / n, sum(r['tok_sum'] for r in runs) / n / 1000))
    return len(d['metric-global-snap']), out


def tpch():
    recs = json.load(gzip.open(TPCH, 'rt', encoding='utf-8'))['records']
    hold = [x for x in recs if x['phase'] == 'holdout' and x['outcome'] != 'error']
    out = {}
    for mode, _ in METHODS:
        xs = [x for x in hold if x['mode'] == mode]
        runs = sorted({x['run'] for x in xs})
        per = []
        for r in runs:
            ys = [x for x in xs if x['run'] == r]
            per.append((sum(x['seconds'] for x in ys) / len(ys),
                        sum(x['input_tokens'] + x['output_tokens'] for x in ys) / len(ys) / 1000))
        pooled = (sum(x['seconds'] for x in xs) / len(xs),
                  sum(x['input_tokens'] + x['output_tokens'] for x in xs) / len(xs) / 1000)
        out[mode] = (per, pooled)
    return len(runs), out


def load():
    am, gn = style.macros('sharing'), style.macros('generality')
    runs_s, syn = synthetic()
    runs_t, tp = tpch()
    style.agree('AmHoldSCond', f'{syn["metric-global-snap"][1][0]:.1f}', am['AmHoldSCond'])
    style.agree('AmHoldSAlone', f'{syn["middle"][1][0]:.1f}', am['AmHoldSAlone'])
    style.agree('AmHoldTokCondK', f'{syn["metric-global-snap"][1][1]:.1f}', am['AmHoldTokCondK'])
    style.agree('AmHoldTokAloneK', f'{syn["middle"][1][1]:.1f}', am['AmHoldTokAloneK'])
    style.agree('GeHoldSCond', f'{tp["metric-global-snap"][1][0]:.1f}', gn['GeHoldSCond'])
    style.agree('GeHoldSNoShare', f'{tp["middle"][1][0]:.1f}', gn['GeHoldSNoShare'])
    gains = [(am['AmHoldSpeedup'], am['AmHoldTokSave']), (gn['GeHoldSpeedup'], gn['GeHoldTokSave'])]
    return [(runs_s, syn), (runs_t, tp)], gains


def figure(lang):
    panels, gains = load()
    T = TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 2, sharey=True, sharex=True,
                        gridspec_kw=dict(left=.10, right=.99, top=.74, bottom=.20, wspace=.06))
    handles = []
    for mode, marker in METHODS:
        label, color = style.method(mode, lang)
        handles.append(Line2D([], [], ls='', color=color, marker=marker, ms=4.2, mfc=color, mec=WHITE, mew=.35,
                              label=label))
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.545, 1.0), ncol=3, handlelength=1.0,
               columnspacing=1.0)
    for k, (ax, (runs, data), (speed, save)) in enumerate(zip(axes, panels, gains)):
        ax.set_title(T['panels'][k].format(runs=runs), pad=3)
        for mode, marker in METHODS:
            _, color = style.method(mode, lang)
            per, pooled = data[mode]
            ax.plot([p[0] for p in per], [p[1] for p in per], ls='', marker=marker, ms=2.6, mfc='none', mec=color,
                    mew=.5, alpha=.85, zorder=2)
            ax.plot([pooled[0]], [pooled[1]], ls='', marker=marker, ms=5.0, mfc=color, mec=WHITE, mew=.45, zorder=4)
        (sa, ta), (sc, tc) = data['middle'][1], data['metric-global-snap'][1]
        ax.annotate('', xy=(sc + 1.2, tc + .25), xytext=(sa - 1.2, ta - .25),
                    arrowprops=dict(arrowstyle='-|>', color=MUTED, lw=.6, mutation_scale=5, shrinkA=0, shrinkB=0),
                    zorder=3)
        # The gain sits below the arrow, clear of the runs that explore alone
        ax.text((sa + sc) / 2 + 1.5, (ta + tc) / 2 - 2.5, T['gain'].format(s=speed, t=save), ha='left', va='top',
                fontsize=mplstyle.SMALL, color=INK, linespacing=1.15)
        ax.set_xlim(0, 72)
        ax.set_ylim(0, 31)
        ax.set_xticks([0, 20, 40, 60])
        ax.set_yticks([0, 10, 20, 30])
        ax.grid(True)
        ax.set_axisbelow(True)
        ax.spines['left'].set_visible(k == 0)
        ax.tick_params(axis='y', length=0 if k else 1.8)
    fig.text(.01, .905, T['y'], color=MUTED, fontsize=mplstyle.LABEL, ha='left', va='top')
    fig.text((.10 + .99) / 2, .02, T['x'], color=MUTED, fontsize=mplstyle.LABEL, ha='center', va='bottom')
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
