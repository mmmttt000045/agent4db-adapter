"""Figure: end-to-end accuracy on two schemas.

Two panels share the y axis: seven methods on synthetic retail (five runs each)
and the three measured methods on TPC-H SF1 (three runs each). The main figure
shows four benign updates, five targeted structural changes, and the two
outside-coverage changes (unit scaling and backup copies); settings in a group weigh
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
from style import FOCUS, INK, MUTED, WHITE  # noqa: E402

NAME = 'two-schemas'
W, H = style.TEXTWIDTH, 52.0
PHASES = {'holdout': ['holdout'], 'benign': ['append', 'backfill', 'correct', 'addcol'],
          'modeled': ['status', 'revision', 'dupload', 'dimhist', 'latekey'],
          'outside': ['unit', 'mirror'],
          'all': ['holdout', 'append', 'backfill', 'correct', 'addcol', 'status', 'revision', 'dupload', 'dimhist',
                  'latekey', 'unit', 'mirror']}
GROUPS = ['benign', 'modeled', 'outside']
# (mode, macro key, marker); keep archive identifiers independent of display names.
METHODS = [('middle', 'NoShare', '^'), ('traj-global', 'Traj', 's'),
           ('traj-verify', 'TrajVerify', 'D'), ('metric-global-schema', 'Schema', 'v'),
           ('metric-global-revoke', 'Revoke', 'P'), ('metric-global-def', 'Def', 'X'),
           ('metric-global-snap', 'Cond', 'o')]
TPCH_METHODS = [m for m in METHODS if m[0] in ('middle', 'traj-global', 'metric-global-snap')]
PANELS = [(style.ROOT / 'exp/2026-10-10-scenarios-q5/scen-stats.json', 'Ds', METHODS),
          (style.ROOT / 'exp/2026-10-11-generality/e2e/scen-stats.json', 'Ge', TPCH_METHODS)]
VALUE_ROW = 5.0   # y of the printed values in the covered-breaks group
TEXT = {
    'en': {'groups': ['Non-breaking\nupdates (4)', 'Targeted structural\nchanges (5)',
                      'Outside coverage\n(unit / backup)'],
           'panels': ['Synthetic retail, {runs} runs', 'TPC-H SF1, {runs} runs'], 'y': 'Accuracy (%)'},
    'zh': {'groups': ['正常更新\n（4 类）', '目标结构变化\n（5 类）', '范围外变化\n（单位／备份副本）'],
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
    for path, prefix, methods in PANELS:
        stats = json.loads(path.read_text(encoding='utf-8'))
        rows = {}
        for mode, key, _ in methods:
            runs = stats['methods'][mode]['runs']
            rows[mode] = {g: group_acc(runs, g) for g in PHASES}
            for g, suffix in (('modeled', 'Modeled'), ('holdout', 'Holdout'), ('benign', 'Benign'), ('all', 'All')):
                style.agree(f'{prefix}/{mode}/{g}', rows[mode][g][0], 100 * stats['methods'][mode][g]['acc'])
                name = f'{prefix}{key}{suffix}'
                if name in printed:
                    style.agree(name, f'{rows[mode][g][0]:.0f}', printed[name])
            # Outside coverage is the equal-weight mean of the two scenario
            # accuracies, not a question-count-weighted pool of unit and mirror.
            outside = 50 * (stats['methods'][mode]['unit']['acc'] + stats['methods'][mode]['mirror']['acc'])
            style.agree(f'{prefix}/{mode}/outside', f'{rows[mode]["outside"][0]:.10f}', f'{outside:.10f}')
            if prefix == 'Ge':
                lo, hi = min(rows[mode]['modeled'][1]), max(rows[mode]['modeled'][1])
                style.agree(f'Ge{key}ModeledMin', f'{lo:.0f}', printed[f'Ge{key}ModeledMin'])
                style.agree(f'Ge{key}ModeledMax', f'{hi:.0f}', printed[f'Ge{key}ModeledMax'])
        panels.append((len(stats['methods']['metric-global-snap']['runs']), methods, rows))
    return panels


def figure(lang):
    panels, T = load(), TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 2, sharey=True,
                        gridspec_kw=dict(left=.05, right=.995, top=.72, bottom=.18,
                                         width_ratios=[1.8, 1], wspace=.10))
    handles = []
    for mode, _, marker in METHODS:
        label, color = style.method(mode, lang)
        handles.append(Line2D([], [], color=color, marker=marker, ms=3.6, mfc=color, mec=WHITE, mew=.35, lw=.9,
                              label=label))
    # Matplotlib fills legend columns first; reorder so rows follow methods 1--7.
    legend = fig.legend(handles=[handles[i] for i in (0, 4, 1, 5, 2, 6, 3)],
                        loc='upper center', bbox_to_anchor=(.52, .99), ncol=4, handlelength=1.4,
                        columnspacing=1.8, labelspacing=.7)
    # MAVRA's entry is set as in Figures 4 and 5: bold, in its colour
    for entry in legend.get_texts():
        if entry.get_text().startswith('MAVRA'):
            entry.set_color(style.method('metric-global-snap', lang)[1])
            entry.set_fontweight('bold')
    for k, (ax, (runs, methods, rows)) in enumerate(zip(axes, panels)):
        ax.set_title(T['panels'][k].format(runs=runs), pad=3)
        focus = GROUPS.index('modeled')
        ax.axvspan(focus - .5, focus + .5, color=FOCUS, lw=0, zorder=0)
        for gi, g in enumerate(GROUPS):
            for mi, (mode, _, marker) in enumerate(methods):
                _, color = style.method(mode, lang)
                pooled, per_run = rows[mode][g]
                x = gi + (mi - (len(methods) - 1) / 2) * (.72 / len(methods))
                ax.plot([x, x], [min(per_run), max(per_run)], color=color, lw=.9, solid_capstyle='butt', zorder=2)
                ax.plot([x], [pooled], ls='', marker=marker, ms=3.6, mfc=color, mec=WHITE, mew=.35, zorder=3)
                if g == 'modeled':
                    # Pooled values in one row at the foot of the shaded group, under their markers
                    ax.text(x, VALUE_ROW, f'{pooled:.0f}', ha='center', va='bottom', fontsize=mplstyle.SMALL,
                            color=INK, fontweight='bold' if mode == 'metric-global-snap' else 'normal')
        ax.set_xlim(-.55, len(GROUPS) - .45)
        ax.set_ylim(0, 105)
        ax.set_xticks(range(len(GROUPS)))
        ax.set_xticklabels(T['groups'])
        ax.tick_params(axis='x', length=0, pad=2)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines['left'].set_visible(k == 0)
        ax.tick_params(axis='y', length=0 if k else 1.8)
    axes[0].set_ylabel(T['y'], labelpad=3)
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
