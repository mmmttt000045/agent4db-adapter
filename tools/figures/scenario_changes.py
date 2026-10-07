"""Figure: accuracy of the user agent by data change, one small dot per run.

Left: the twelve settings in the order of tools/paper-results.py, grouped by
the condition the change targets (shaded bands). For six methods, one small
dot per independent run and a large marker at the accuracy over the runs'
tasks; a hollow marker means that at least 25% of the tasks used a stale
definition. Right: invalidations and published repairs per run for the
methods that maintain definitions. Data: exp/2026-10-02-scenarios-ds/
scen-stats.json (per-run counts written by tools/scen-stats.py), cross-checked
against paper-results.json and against every value the text prints (\\ScenAcc*
in gen/numbers.tex, \\Ds* in gen/scen-ds.tex).
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import GRID, INK, MUTED  # noqa: E402

NAME = 'scenario-changes'
W, H = style.TEXTWIDTH, 70.0
STATS = style.ROOT / 'exp/2026-10-02-scenarios-ds/scen-stats.json'
RESULTS = style.ROOT / 'exp/2026-10-02-scenarios-ds/paper-results.json'
STALE = .25                      # share of tasks that used a stale definition

_spec = importlib.util.spec_from_file_location('paper_results', style.ROOT / 'tools/paper-results.py')
paper_results = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paper_results)
PHASES, CLASSES = paper_results.PHASES, paper_results.CLASSES

SHOWN = ['middle', 'traj-global', 'traj-verify', 'metric-global-noguard', 'metric-global-def',
         'metric-global-snap']
MAINTAINERS = ['metric-global-revoke', 'metric-global-def', 'metric-global-exref', 'metric-global-snap']
# Macro keys of tools/scen-stats.py and tools/paper-results.py: \Ds<key>*, \ScenAcc<key>*.
KEY = {'middle': 'NoShare', 'traj-global': 'Traj', 'traj-verify': 'TrajVerify',
       'metric-global-noguard': 'Noguard', 'metric-global-schema': 'Schema',
       'metric-global-revoke': 'Revoke', 'metric-global-def': 'Def', 'metric-global-snap': 'Cond',
       'metric-global-exref': 'CondCur', 'metric-global': 'CondGold'}
SHORT = {  # two-line tick labels for the twelve settings
    'en': {'holdout': 'Held-out', 'append': 'Append', 'backfill': 'Late-\narriving',
           'correct': 'In-place\nfix', 'addcol': 'New\ncolumn', 'status': 'Status\nrows',
           'revision': 'Restate-\nment', 'dupload': 'Duplicate\nload', 'dimhist': 'SCD\nType 2',
           'latekey': 'Date-key\nformat', 'unit': 'Unit\nchange', 'mirror': 'Backup\ncopy'},
    'zh': {'holdout': '留出', 'append': '正常\n追加', 'backfill': '迟到\n事实', 'correct': '原地\n更正',
           'addcol': '新增\n无关列', 'status': '状态\n变更行', 'revision': '多版本\n更正',
           'dupload': '重复\n加载', 'dimhist': '缓慢\n变化维', 'latekey': '日期键\n格式',
           'unit': '金额\n单位', 'mirror': '备份\n副本'},
}
TEXT = {
    'en': {'y': 'Accuracy of the user agent (%)', 'run': 'one run',
           'stale': 'hollow: at least 25% of the tasks used a stale definition',
           'title_b': 'Invalidations (light) and\npublished repairs (solid)\nper run',
           'b_labels': {'metric-global-revoke': 'Invalidate-on-write', 'metric-global-def': 'Definition-level',
                        'metric-global-exref': 'MAVRA, G8 on\ncurrent data', 'metric-global-snap': 'MAVRA'}},
    'zh': {'y': '用户端智能体正确率（%）', 'run': '一次运行',
           'stale': '空心：至少 25% 的题使用了过期定义',
           'title_b': '每次运行的失效数（浅）\n与发布的修复数（深）\n',
           'b_labels': {'metric-global-revoke': '写入即失效', 'metric-global-def': '定义级',
                        'metric-global-exref': 'MAVRA，G8 用\n当前数据', 'metric-global-snap': 'MAVRA'}},
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
                  left=.045, right=.985, top=.80, bottom=.19)

    # ── Left: accuracy by data change ──────────────────────────────────────────
    ax = fig.add_subplot(gs[0])
    offsets = np.linspace(-.36, .36, len(SHOWN))
    rng = np.random.default_rng(7)
    prev, band = None, 0
    for i, (phase, cls, *_) in enumerate(PHASES):
        if cls != prev:
            span = sum(1 for _, c, *_ in PHASES if c == cls)
            if band % 2:
                ax.axvspan(i - .5, i + span - .5, color='#F3F2EF', lw=0, zorder=0)
            level = 105 if span > 1 or band % 2 == 0 else 113
            ax.text(i + span / 2 - .5, level, CLASSES[cls][zh], ha='center', va='bottom',
                    fontsize=mplstyle.LABEL, color=INK, fontweight='bold', clip_on=False)
            if span == 1:
                ax.plot([i, i], [103, level - 1], color=MUTED, lw=.4, clip_on=False)
            band += 1
        prev = cls
        for off, mode in zip(offsets, SHOWN):
            runs, mean, stale = cells[mode, phase]
            if mean is None:
                continue
            x, color = i + off, mplstyle.color(mode)
            ax.scatter(x + rng.uniform(-.03, .03, len(runs)), runs, s=4, color=color, alpha=.45,
                       lw=0, zorder=2)
            ax.scatter([x], [mean], s=17, facecolor='white' if stale else color, edgecolor=color,
                       lw=.7 if stale else .35, zorder=3)
    ax.set_xlim(-.5, len(PHASES) - .5)
    ax.set_ylim(-3, 103)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.set_xticks(range(len(PHASES)))
    ax.set_xticklabels([SHORT[lang][p] for p, *_ in PHASES], linespacing=.95)
    ax.tick_params(axis='x', length=0, pad=2.5)
    ax.spines['bottom'].set_visible(False)
    ax.set_ylabel(T['y'])

    handles = [Line2D([], [], marker='o', ls='', ms=3.6, color=mplstyle.color(m), label=mplstyle.name(m, lang))
               for m in SHOWN]
    handles.append(Line2D([], [], marker='o', ls='', ms=1.9, color=MUTED, alpha=.6, label=T['run']))
    handles.append(Line2D([], [], marker='o', ls='', ms=3.6, mfc='white', mec=MUTED, mew=.7, label=T['stale']))
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.04, 1.0), ncol=4)

    # ── Right: invalidations and repairs per run ──────────────────────────────
    ax2 = fig.add_subplot(gs[1])
    ys = np.arange(len(MAINTAINERS))[::-1]
    for y, mode in zip(ys, MAINTAINERS):
        rev, rep, runs = events[mode]
        color = mplstyle.color(mode)
        ax2.barh(y + .18, rev, height=.33, color=color, alpha=.35, lw=0)
        ax2.barh(y - .18, rep, height=.33, color=color, lw=0)
        ax2.scatter([r for r, _ in runs], [y + .18] * len(runs), s=3.5, color=INK, alpha=.6, lw=0, zorder=3)
        ax2.scatter([p for _, p in runs], [y - .18] * len(runs), s=3.5, color=INK, alpha=.6, lw=0, zorder=3)
        ax2.text(max([rev] + [r for r, _ in runs]) + 1.0, y + .18, f'{rev:.1f}', va='center',
                 fontsize=mplstyle.TICK, color=INK)
        ax2.text(max([rep] + [p for _, p in runs]) + 1.0, y - .18, f'{rep:.1f}', va='center',
                 fontsize=mplstyle.TICK, color=INK)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([T['b_labels'][m] for m in MAINTAINERS], linespacing=.95)
    ax2.tick_params(axis='y', length=0, pad=2.5)
    ax2.set_ylim(-.6, len(MAINTAINERS) - .4)
    ax2.set_xlim(0, 56)
    ax2.set_xticks([0, 20, 40])
    ax2.xaxis.grid(True)
    ax2.set_axisbelow(True)
    ax2.spines['left'].set_visible(False)
    ax2.set_title(T['title_b'], loc='left', pad=4, linespacing=1.0)
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
