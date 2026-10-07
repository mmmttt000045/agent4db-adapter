"""Figure: accuracy of the user agent by data change, with the spread over runs.

Left: the twelve settings in the order of tools/paper-results.py, grouped by
the condition the change targets (brackets under the axis). For the baselines
and MAVRA, one marker per setting at the accuracy over the three independent
runs, a thin line behind it spanning the three runs, and a red ring when at
least 25% of the tasks used a stale definition. Right: invalidations and
published repairs per run for the methods that keep definitions, with the
spread over runs. Data: exp/2026-10-02-scenarios-ds/scen-stats.json (per-run
counts written by tools/scen-stats.py), cross-checked against
paper-results.json and against every value the text prints (\\ScenAcc* in
gen/numbers.tex, \\Ds* in gen/scen-ds.tex).
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from matplotlib import transforms  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import GRID, INK, MUTED, RED  # noqa: E402

NAME = 'scenario-changes'
W, H = style.TEXTWIDTH, 76.0
STATS = style.ROOT / 'exp/2026-10-02-scenarios-ds/scen-stats.json'
RESULTS = style.ROOT / 'exp/2026-10-02-scenarios-ds/paper-results.json'
STALE = .25                      # share of tasks that used a stale definition

_spec = importlib.util.spec_from_file_location('paper_results', style.ROOT / 'tools/paper-results.py')
paper_results = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paper_results)
PHASES, CLASSES = paper_results.PHASES, paper_results.CLASSES

# Left panel: the baselines and MAVRA. The ablations are in the right panel and the text.
SHOWN = ['middle', 'traj-global', 'traj-verify', 'metric-global-schema', 'metric-global-revoke',
         'metric-global-snap']
MARKER = {'traj-verify': 'D'}    # the variant of example retrieval keeps its hue, changes shape
# Legend order puts the variant right under its base method; its legend label is the suffix.
LEGEND = ['traj-global', 'traj-verify', 'middle', 'metric-global-schema', 'metric-global-revoke',
          'metric-global-snap']
LEGEND_LABEL = {'traj-verify': {'en': '+ self-verification', 'zh': '+ 自行核验'}}
MAINTAINERS = ['metric-global-revoke', 'metric-global-snap', 'metric-global-def', 'metric-global-exref']
# Macro keys of tools/scen-stats.py and tools/paper-results.py: \Ds<key>*, \ScenAcc<key>*.
KEY = {'middle': 'NoShare', 'traj-global': 'Traj', 'traj-verify': 'TrajVerify',
       'metric-global-noguard': 'Noguard', 'metric-global-schema': 'Schema',
       'metric-global-revoke': 'Revoke', 'metric-global-def': 'Def', 'metric-global-snap': 'Cond',
       'metric-global-exref': 'CondCur', 'metric-global': 'CondGold'}
SHORT = {  # tick labels for the twelve settings; line breaks only between words
    'en': {'holdout': 'Held-out', 'append': 'Append', 'backfill': 'Late\narriving',
           'correct': 'In-place\nfix', 'addcol': 'New\ncolumn', 'status': 'Status\nrows',
           'revision': 'Restatement', 'dupload': 'Duplicate\nload', 'dimhist': 'SCD\nType 2',
           'latekey': 'Date-key\nformat', 'unit': 'Unit\nchange', 'mirror': 'Backup\ncopy'},
    'zh': {'holdout': '留出', 'append': '正常\n追加', 'backfill': '迟到\n事实', 'correct': '原地\n更正',
           'addcol': '新增\n无关列', 'status': '状态\n变更行', 'revision': '多版本\n更正',
           'dupload': '重复\n加载', 'dimhist': '缓慢\n变化维', 'latekey': '日期键\n格式',
           'unit': '金额\n单位', 'mirror': '备份\n副本'},
}
TEXT = {
    'en': {'y': 'Accuracy of the user agent (%)', 'range': 'range of the three runs',
           'stale': 'red ring: stale definition in ≥25% of tasks',
           'maint_title': 'Maintenance per run\n(methods that keep definitions)',
           'inval': 'invalidations', 'repairs': 'published repairs',
           'b_labels': {'metric-global-revoke': 'Invalidate on\nevery write', 'metric-global-snap': 'MAVRA',
                        'metric-global-def': 'Full recheck\nper definition',
                        'metric-global-exref': 'MAVRA, regression\non current data'}},
    'zh': {'y': '用户端智能体正确率（%）', 'range': '三次运行的范围',
           'stale': '红圈：≥25% 的题使用了过期定义',
           'maint_title': '每次运行的维护\n（维护定义的方法）',
           'inval': '失效数', 'repairs': '发布的修复数',
           'b_labels': {'metric-global-revoke': '每次写入\n即失效', 'metric-global-snap': 'MAVRA',
                        'metric-global-def': '整定义重查',
                        'metric-global-exref': 'MAVRA，回归测\n试用当前数据'}},
}


def load():
    """Per (method, phase): run accuracies, pooled accuracy, stale flag; per maintainer: events per run."""
    methods = json.loads(STATS.read_text(encoding='utf-8'))['methods']
    results = json.loads(RESULTS.read_text(encoding='utf-8'))
    numbers, intervals = style.macros('numbers'), style.macros('scen-ds')
    models = sorted({key.split('|')[0] for key in results['accuracy']})
    cells = {}
    for mode in SHOWN:
        runs = methods[mode]['runs']
        for phase, *_ in PHASES:
            counts = [r['acc'].get(phase, [0, 0]) for r in runs]
            k, n = sum(c[0] for c in counts), sum(c[1] for c in counts)
            stale = sum(r['stale'].get(phase, 0) for r in runs)
            per_run = [100 * c[0] / c[1] for c in counts if c[1]]
            mean = 100 * k / n if n else None
            # The same pooled accuracy from the other archive (tools/paper-results.py).
            k2, n2 = (sum(x) for x in zip(*(results['accuracy'].get(f'{m}|{mode}|{phase}', (0, 0)) for m in models)))
            style.agree(f'{mode}/{phase} accuracy', f'{k}/{n}', f'{k2}/{n2}')
            name = f'ScenAcc{KEY[mode]}{phase.capitalize()}'
            if name in numbers and mean is not None:
                style.agree(name, f'{mean:.0f}', numbers[name])
            cells[mode, phase] = (per_run, mean, n > 0 and stale / n >= STALE)
        means = [cells[mode, p][1] for p, *_ in PHASES if cells[mode, p][1] is not None]
        style.agree(f'ScenAcc{KEY[mode]}', f'{sum(means) / len(means):.0f}', numbers[f'ScenAcc{KEY[mode]}'])
        covered = methods[mode]['modeled']
        for suffix, v in (('', covered['acc']), ('Lo', covered['ci95'][0]), ('Hi', covered['ci95'][1])):
            style.agree(f'Ds{KEY[mode]}Modeled{suffix}', f'{100 * v:.0f}', intervals[f'Ds{KEY[mode]}Modeled{suffix}'])
    events = {}
    for mode in MAINTAINERS:
        row = methods[mode]
        rev, rep = row['revoked_per_cell'], row['repaired_per_cell']
        style.agree(f'Ds{KEY[mode]}Revoked', f'{rev:.1f}', intervals[f'Ds{KEY[mode]}Revoked'])
        style.agree(f'Ds{KEY[mode]}Repaired', f'{rep:.1f}', intervals[f'Ds{KEY[mode]}Repaired'])
        events[mode] = (rev, rep, [(r['revoked'], r['repaired']) for r in row['runs']])
    return cells, events


def figure(lang):
    cells, events = load()
    T, zh = TEXT[lang], lang == 'zh'
    fig = mplstyle.figure(W, H)
    gs = GridSpec(1, 2, figure=fig, width_ratios=[3.35, 1.0], wspace=.27,
                  left=.045, right=.985, top=.80, bottom=.31)

    # ── Left: accuracy by data change ──────────────────────────────────────────
    ax = fig.add_subplot(gs[0])
    n = len(PHASES)
    groups = []                                   # [class, first index, last index]
    for i, (_, cls, *_) in enumerate(PHASES):
        if groups and groups[-1][0] == cls:
            groups[-1][2] = i
        else:
            groups.append([cls, i, i])
    for i in range(n - 1):
        ax.axvline(i + .5, color=GRID, lw=.4, zorder=0)
    for _, i0, _ in groups[1:]:
        ax.axvline(i0 - .5, color=MUTED, lw=.5, zorder=0)
    offsets = np.linspace(-.3, .3, len(SHOWN))
    for i, (phase, *_) in enumerate(PHASES):
        for off, mode in zip(offsets, SHOWN):
            runs, mean, stale = cells[mode, phase]
            if mean is None:
                continue
            x, color = i + off, mplstyle.color(mode)
            if runs and max(runs) - min(runs) > .5:
                ax.plot([x, x], [min(runs), max(runs)], color=color, lw=.9, alpha=.8,
                        solid_capstyle='butt', zorder=2)
            marker = MARKER.get(mode, 'o')
            ax.scatter([x], [mean], s=18 if marker == 'D' else 20, marker=marker, facecolor=color,
                       edgecolor=RED if stale else 'white', lw=1.0 if stale else .35, zorder=3)
    ax.set_xlim(-.5, n - .5)
    ax.set_ylim(-3, 103)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.set_xticks(range(n))
    ax.set_xticklabels([SHORT[lang][p] for p, *_ in PHASES], linespacing=.95)
    ax.tick_params(axis='x', length=0, pad=2.5)
    ax.spines['bottom'].set_visible(False)
    ax.set_ylabel(T['y'])
    # Class brackets under the tick labels: a two-level categorical axis.
    below = transforms.blended_transform_factory(ax.transData, ax.transAxes)
    yb, singles = -.17, 0
    for cls, i0, i1 in groups:
        x0, x1 = i0 - .42, i1 + .42
        ax.plot([x0, x0, x1, x1], [yb + .03, yb, yb, yb + .03], transform=below, color=MUTED, lw=.6,
                clip_on=False, solid_capstyle='butt')
        # Labels of consecutive one-slot classes alternate between two rows so they do not collide.
        drop = .105 if i0 == i1 and singles % 2 else 0
        singles = singles + 1 if i0 == i1 else 0
        ax.text((i0 + i1) / 2, yb - .03 - drop, CLASSES[cls][zh], transform=below, ha='center', va='top',
                fontsize=mplstyle.LABEL, color=INK, fontweight='bold', clip_on=False)

    handles = [Line2D([], [], marker=MARKER.get(m, 'o'), ls='', ms=3.6 if MARKER.get(m) else 4.0,
                      color=mplstyle.color(m), label=LEGEND_LABEL.get(m, {}).get(lang, mplstyle.name(m, lang)))
               for m in LEGEND]
    handles.append(Line2D([], [], color=MUTED, lw=.9, label=T['range']))
    handles.append(Line2D([], [], marker='o', ls='', ms=4.0, mfc=MUTED, mec=RED, mew=1.0, label=T['stale']))
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.02, 1.0), ncol=4, columnspacing=1.0)

    # ── Right: invalidations and repairs per run ──────────────────────────────
    ax2 = fig.add_subplot(gs[1])
    ys = np.arange(len(MAINTAINERS))[::-1]
    xmax = 60
    for y, mode in zip(ys, MAINTAINERS):
        rev, rep, runs = events[mode]
        color = mplstyle.color(mode)
        for dy, value, values, alpha in ((.18, rev, [r for r, _ in runs], .35),
                                         (-.18, rep, [p for _, p in runs], 1.0)):
            if value > 0:
                ax2.barh(y + dy, value, height=.33, color=color, alpha=alpha, lw=0, zorder=2)
                if max(values) - min(values) > .05:
                    ax2.plot([min(values), max(values)], [y + dy, y + dy], color=INK, lw=.8,
                             solid_capstyle='butt', zorder=3)
            ax2.text(xmax - .8, y + dy, f'{value:.1f}' if value else '0', ha='right', va='center',
                     fontsize=mplstyle.TICK, color=INK)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([T['b_labels'][m] for m in MAINTAINERS], linespacing=.95)
    ax2.tick_params(axis='y', length=0, pad=2.5)
    ax2.set_ylim(-.6, len(MAINTAINERS) - .4)
    ax2.set_xlim(0, xmax)
    ax2.set_xticks([0, 20, 40])
    ax2.xaxis.grid(True)
    ax2.set_axisbelow(True)
    ax2.spines['left'].set_visible(False)
    # Title and shade legend sit under the panel, so the header band belongs to the left legend.
    shades = [Patch(facecolor=MUTED, alpha=.35, label=T['inval']), Patch(facecolor=MUTED, label=T['repairs'])]
    pos = ax2.get_position()
    legend = fig.legend(handles=shades, loc='upper left', bbox_to_anchor=(pos.x0 - .05, pos.y0 - .085),
                        ncol=1, title=T['maint_title'], alignment='left', handlelength=1.2, handleheight=.8)
    legend.get_title().set_fontsize(mplstyle.TITLE)
    legend.get_title().set_fontweight('bold')
    legend.get_title().set_color(INK)
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
