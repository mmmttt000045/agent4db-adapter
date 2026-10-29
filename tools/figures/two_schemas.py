"""End-to-end accuracy on synthetic retail and TPC-H SF1.

Grouped bars show pooled accuracy, with settings weighted equally as in
tools/scen-stats.py. Capped error bars span per-run accuracies. The four groups,
original data sources, and macro checks are unchanged.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.patches import Patch  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402

NAME = 'two-schemas'
W, H = style.COLUMN, 52.0
PHASES = {'holdout': ['holdout'], 'benign': ['append', 'backfill', 'correct', 'addcol'],
          'modeled': ['status', 'revision', 'dupload', 'dimhist', 'latekey'],
          'all': ['holdout', 'append', 'backfill', 'correct', 'addcol', 'status', 'revision', 'dupload', 'dimhist',
                  'latekey', 'unit', 'mirror']}
GROUPS = ['holdout', 'benign', 'modeled', 'all']
# (mode, macro key of the synthetic study, macro key of TPC-H, marker)
METHODS = [('middle', 'NoShare', 'NoShare', '^'),
           ('metric-global-snap', 'Cond', 'Cond', 'o')]
PANELS = [(style.ROOT / 'exp/2026-10-10-scenarios-q5/scen-stats.json', 'Ds'),
          (style.ROOT / 'exp/2026-10-11-generality/e2e/scen-stats.json', 'Ge')]
TEXT = {
    'en': {'groups': ['Held-\nout', 'Non-\nbreaking', 'Covered\nbreaks', 'All\nsettings'],
           'panels': ['(a) Synthetic retail', '(b) TPC-H SF1'], 'y': 'Accuracy (%)'},
    'zh': {'groups': ['留出题', '正常\n更新', '覆盖的\n破坏', '全部\n情形'],
           'panels': ['(a) 合成零售数据', '(b) TPC-H SF1'], 'y': '正确率（%）'},
}


def group_acc(runs, group):
    """Pooled and per-run accuracy (%) of a group, settings weighted equally."""
    phases = PHASES[group]
    pooled = sum(sum(r['acc'][p][0] for r in runs) / sum(r['acc'][p][1] for r in runs) for p in phases) / len(phases)
    per_run = [sum(r['acc'][p][0] / r['acc'][p][1] for p in phases) / len(phases) for r in runs]
    return 100 * pooled, [100 * x for x in per_run]


def load():
    printed = {**style.macros('scen-ds'), **style.macros('generality')}
    panels = []
    for path, prefix in PANELS:
        stats = json.loads(path.read_text(encoding='utf-8'))
        rows = {}
        for mode, ds_key, ge_key, _ in METHODS:
            runs = stats['methods'][mode]['runs']
            rows[mode] = {g: group_acc(runs, g) for g in GROUPS}
            key = ds_key if prefix == 'Ds' else ge_key
            for g, suffix in (('modeled', 'Modeled'), ('holdout', 'Holdout')):
                name = f'{prefix}{key}{suffix}'
                if name in printed:
                    style.agree(name, f'{rows[mode][g][0]:.0f}', printed[name])
            if prefix == 'Ge':
                lo, hi = min(rows[mode]['modeled'][1]), max(rows[mode]['modeled'][1])
                style.agree(f'Ge{key}ModeledMin', f'{lo:.0f}', printed[f'Ge{key}ModeledMin'])
                style.agree(f'Ge{key}ModeledMax', f'{hi:.0f}', printed[f'Ge{key}ModeledMax'])
        panels.append((len(stats['methods']['metric-global-snap']['runs']), rows))
    return panels


def figure(lang):
    panels, T = load(), TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 2, sharey=True,
                        gridspec_kw=dict(left=.12, right=.99, top=.86, bottom=.23, wspace=.24))
    hatches = {'middle': '////', 'traj-global': r'\\\\', 'metric-global-snap': '....'}
    handles = [Patch(**mplstyle.bar_style(mode, hatches[mode]), label=mplstyle.name(mode, lang))
               for mode, _, _, _ in METHODS]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.51, 1.0), ncol=3,
               handlelength=1.2, columnspacing=.9, fontsize=mplstyle.SMALL)
    width = .30
    for k, (ax, (_, rows)) in enumerate(zip(axes, panels)):
        for mi, (mode, _, _, _) in enumerate(METHODS):
            values = [rows[mode][g][0] for g in GROUPS]
            lows = [min(rows[mode][g][1]) for g in GROUPS]
            highs = [max(rows[mode][g][1]) for g in GROUPS]
            xs = [gi + (mi - (len(METHODS) - 1) / 2) * width for gi in range(len(GROUPS))]
            ax.bar(xs, values, width=width, **mplstyle.bar_style(mode, hatches[mode]), zorder=2)
            ax.errorbar(xs, values,
                        yerr=[[v - low for v, low in zip(values, lows)],
                              [high - v for high, v in zip(highs, values)]],
                        fmt='none', ecolor='black', elinewidth=.45, capsize=1.0,
                        capthick=.45, zorder=3)
        ax.set_xlim(-.55, len(GROUPS) - .45)
        ax.set_ylim(0, 105)
        ax.set_xticks(range(len(GROUPS)), T['groups'])
        ax.tick_params(axis='x', length=0, labelsize=mplstyle.SMALL)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.yaxis.grid(True)
        box = ax.get_position()
        fig.text((box.x0 + box.x1) / 2, .025, T['panels'][k],
                 ha='center', va='bottom', fontsize=mplstyle.LABEL)
    axes[0].set_ylabel(T['y'])
    return fig

if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
