"""Per-question time and token cost on held-out queries over static data.

Two grouped-bar panels separate agent-session time from token usage. Bars pool
all questions for a method; capped error bars span the per-run means. Synthetic
retail has five runs, TPC-H SF1 three. Sources and macro checks are unchanged.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.patches import Patch  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402

NAME = 'consumer-cost'
W, H = style.COLUMN, 49.0
SYN = style.ROOT / 'exp/2026-10-10-scenarios-q5/holdout-cost.json'
TPCH = style.ROOT / 'exp/2026-10-11-generality/e2e/outcomes.json.gz'
METHODS = [('middle', '^'), ('metric-global-snap', 'o')]
TEXT = {
    'en': {'datasets': ['Synthetic\nretail', 'TPC-H\nSF1'],
           'y': ['Time per question (s)', 'Tokens per question (k)'],
           'panels': ['(a) Agent-session time', '(b) Token cost']},
    'zh': {'datasets': ['合成零售', 'TPC-H\nSF1'],
           'y': ['每题时间（秒）', '每题 token（千）'],
           'panels': ['(a) 智能体会话时间', '(b) token 代价']},
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
    panels, _ = load()
    T = TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 2, gridspec_kw=dict(left=.13, right=.985, top=.86, bottom=.23, wspace=.64))
    hatches = {'middle': '////', 'metric-global-snap': '....'}
    handles = [Patch(**mplstyle.bar_style(mode, hatches[mode]), label=mplstyle.name(mode, lang))
               for mode, _ in METHODS]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.55, 1.0), ncol=2,
               handlelength=1.5, columnspacing=1.7)
    width = .30
    for k, ax in enumerate(axes):
        for mi, (mode, _) in enumerate(METHODS):
            values, lows, highs = [], [], []
            for _, data in panels:
                per, pooled = data[mode]
                values.append(pooled[k])
                lows.append(min(p[k] for p in per))
                highs.append(max(p[k] for p in per))
            xs = [i + (mi - .5) * width for i in range(len(panels))]
            ax.bar(xs, values, width=width, **mplstyle.bar_style(mode, hatches[mode]), zorder=2)
            ax.errorbar(xs, values,
                        yerr=[[v - low for v, low in zip(values, lows)],
                              [high - v for high, v in zip(highs, values)]],
                        fmt='none', ecolor='black', elinewidth=.55, capsize=1.8,
                        capthick=.55, zorder=3)
        ax.set_xlim(-.55, len(panels) - .45)
        ax.set_ylim(0, 75 if k == 0 else 32)
        ax.set_yticks([0, 20, 40, 60] if k == 0 else [0, 10, 20, 30])
        ax.set_xticks(range(len(panels)), T['datasets'])
        ax.tick_params(axis='x', length=0)
        ax.set_ylabel(T['y'][k])
        ax.yaxis.grid(True)
        box = ax.get_position()
        fig.text((box.x0 + box.x1) / 2, .025, T['panels'][k],
                 ha='center', va='bottom', fontsize=mplstyle.LABEL)
    return fig

if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
