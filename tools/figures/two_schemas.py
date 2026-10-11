"""Figure: end-to-end accuracy on two schemas.

Two panels share the y axis: the synthetic retail fixture (five runs per method)
and TPC-H SF1 (three runs per method). Each group pools settings of one class:
held-out questions, the four benign updates, the five breaking changes the
conditions cover, and all twelve settings; settings within a group weigh
equally, as in tools/scen-stats.py. For every method a vertical line spans the
per-run accuracies and a marker gives the pooled value; marker shapes repeat the
method colours so that identity does not rest on colour. The covered-breaks
group is shaded, with its pooled values printed in a row at its foot.
Data: exp/2026-10-10-scenarios-q5/scen-stats.json and
exp/2026-10-11-generality/e2e/scen-stats.json (per-run counts in `runs`),
checked against the \\Ds* and \\Ge* macros the text prints.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.lines import Line2D  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import ACC_PALE, INK, MUTED, WHITE  # noqa: E402

NAME = 'two-schemas'
W, H = style.COLUMN, 42.0
PHASES = {'holdout': ['holdout'], 'benign': ['append', 'backfill', 'correct', 'addcol'],
          'modeled': ['status', 'revision', 'dupload', 'dimhist', 'latekey'],
          'all': ['holdout', 'append', 'backfill', 'correct', 'addcol', 'status', 'revision', 'dupload', 'dimhist',
                  'latekey', 'unit', 'mirror']}
GROUPS = ['holdout', 'benign', 'modeled', 'all']
# (mode, macro key of the synthetic study, macro key of TPC-H, marker)
METHODS = [('middle', 'NoShare', 'NoShare', '^'), ('traj-global', 'Traj', 'Traj', 's'),
           ('metric-global-snap', 'Cond', 'Cond', 'o')]
PANELS = [(style.ROOT / 'exp/2026-10-10-scenarios-q5/scen-stats.json', 'Ds'),
          (style.ROOT / 'exp/2026-10-11-generality/e2e/scen-stats.json', 'Ge')]
OFFSET = .26
VALUE_ROW = 15.5   # y of the printed values in the covered-breaks group
TEXT = {
    'en': {'groups': ['Held-\nout', 'Non-\nbreaking', 'Covered\nbreaks', 'All\nsettings'],
           'panels': ['Synthetic retail, {runs} runs', 'TPC-H SF1, {runs} runs'], 'y': 'Accuracy (%)'},
    'zh': {'groups': ['留出题', '正常更新', '覆盖的\n破坏', '全部\n情形'],
           'panels': ['合成零售数据，{runs} 次运行', 'TPC-H SF1，{runs} 次运行'], 'y': '正确率（%）'},
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
    axes = fig.subplots(1, 2, sharey=True, gridspec_kw=dict(left=.085, right=.995, top=.74, bottom=.17, wspace=.06))
    handles = []
    for mode, _, _, marker in METHODS:
        label, color = style.method(mode, lang)
        handles.append(Line2D([], [], color=color, marker=marker, ms=3.6, mfc=color, mec=WHITE, mew=.35, lw=.9,
                              label=label))
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.54, 1.0), ncol=3, handlelength=1.4,
               columnspacing=1.0)
    for k, (ax, (runs, rows)) in enumerate(zip(axes, panels)):
        ax.set_title(T['panels'][k].format(runs=runs), pad=3)
        ax.axvspan(1.5, 2.5, color=ACC_PALE, lw=0, zorder=0)
        for gi, g in enumerate(GROUPS):
            for mi, (mode, _, _, marker) in enumerate(METHODS):
                _, color = style.method(mode, lang)
                pooled, per_run = rows[mode][g]
                x = gi + (mi - 1) * OFFSET
                ax.plot([x, x], [min(per_run), max(per_run)], color=color, lw=.9, solid_capstyle='butt', zorder=2)
                ax.plot([x], [pooled], ls='', marker=marker, ms=3.6, mfc=color, mec=WHITE, mew=.35, zorder=3)
                if g == 'modeled':
                    # Pooled values in one row at the foot of the shaded group, under their markers
                    ax.text(x, VALUE_ROW, f'{pooled:.0f}', ha='center', va='bottom', fontsize=mplstyle.SMALL,
                            color=INK, fontweight='bold' if mode == 'metric-global-snap' else 'normal')
        ax.set_xlim(-.55, len(GROUPS) - .45)
        ax.set_ylim(14, 104)
        ax.set_xticks(range(len(GROUPS)))
        ax.set_xticklabels(T['groups'])
        ax.tick_params(axis='x', length=0, pad=2)
        ax.set_yticks([25, 50, 75, 100])
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines['left'].set_visible(k == 0)
        ax.tick_params(axis='y', length=0 if k else 1.8)
    fig.text(.01, .905, T['y'], color=MUTED, fontsize=mplstyle.LABEL, ha='left', va='top')
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
