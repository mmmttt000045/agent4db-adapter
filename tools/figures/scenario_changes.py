"""Figure: accuracy of the user agent by data change, as grouped bars.

One group per setting, in three classes under the axis: the held-out
questions and the four benign updates (pooled); the five breaks covered by a
condition, one by one and pooled; and the two changes outside the guarantee.
Five methods per group, in the order of Table 2 and grouped in the legend by
role (no sharing; shared but not maintained, the existing approaches; shared
and maintained), five runs each. The full recheck per definition, MAVRA
without check-result reuse, answers within a point of MAVRA on every setting
and stays in the text and the cost figure; the self-verification variant of
example retrieval and the two MAVRA regression variants are reported in the
text. The bar is the accuracy pooled over the five independent runs, the
line its 95% bootstrap interval over runs, and a hatched bar marks a setting
in which at least 25% of the tasks used a stale definition. Data:
exp/2026-10-10-scenarios-q5/scen-stats.json (per-run counts written by
tools/scen-stats.py, with the group intervals the text prints), cross-checked
against paper-results.json and against every value the text prints
(\\ScenAcc* in gen/numbers.tex, \\Ds* in gen/scen-ds.tex); the intervals of
single settings are bootstrapped here with the same resampling of runs.
"""
import importlib.util
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib import pyplot as plt, transforms  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import ACC_DK, FIELD, INK, MUTED, RED  # noqa: E402

NAME = 'scenario-changes'
W, H = style.TEXTWIDTH, 65.0
STATS = style.ROOT / 'exp/2026-10-10-scenarios-q5/scen-stats.json'
RESULTS = style.ROOT / 'exp/2026-10-10-scenarios-q5/paper-results.json'
STALE = .25                      # share of tasks that used a stale definition
REPS, SEED = 4000, 20261002      # as tools/scen-stats.py


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, style.ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paper_results = _load('paper_results', 'tools/paper-results.py')
scen_stats = _load('scen_stats', 'tools/scen-stats.py')
PHASES = paper_results.PHASES

# Bars of every group, in the order of Table 2, and their roles for the legend: the lower bound without
# sharing; the existing ways to share, which do not check what they serve; and maintained sharing. The
# full recheck per definition (MAVRA without check-result reuse) answers within a point of MAVRA on every
# setting and is left to the text and to the cost figure.
METHODS = ['middle', 'traj-global', 'metric-global-schema', 'metric-global-revoke', 'metric-global-snap']
ROLES = [('none', ['middle']), ('unmaintained', ['traj-global', 'metric-global-schema']),
         ('maintained', ['metric-global-revoke', 'metric-global-snap'])]
OURS = 'metric-global-snap'
# Macro keys of tools/scen-stats.py and tools/paper-results.py: \Ds<key>*, \ScenAcc<key>*.
KEY = {'middle': 'NoShare', 'traj-global': 'Traj', 'metric-global-schema': 'Schema',
       'metric-global-revoke': 'Revoke', 'metric-global-def': 'Def', 'metric-global-snap': 'Cond'}
# (group, phases, class, macro group whose interval the text prints, or None)
GROUPS = [('holdout', ['holdout'], 'none', 'Holdout'),
          ('benign', ['append', 'backfill', 'correct', 'addcol'], 'none', 'Benign'),
          ('status', ['status'], 'covered', None),
          ('revision', ['revision'], 'covered', None),
          ('dupload', ['dupload'], 'covered', None),
          ('dimhist', ['dimhist'], 'covered', None),
          ('latekey', ['latekey'], 'covered', None),
          ('covered', ['status', 'revision', 'dupload', 'dimhist', 'latekey'], 'covered', 'Modeled'),
          ('unit', ['unit'], 'outside', 'Unit'),
          ('mirror', ['mirror'], 'outside', 'Mirror')]
POOLED = {'benign', 'covered'}
TEXT = {
    'en': {'groups': {'holdout': 'Held-out', 'benign': 'Benign\nupdates (4)', 'status': 'Status\nrows',
                      'revision': 'Restated\nsales', 'dupload': 'Duplicate\nload', 'dimhist': 'SCD\nType 2',
                      'latekey': 'Date-key\nformat', 'covered': 'All covered\nbreaks', 'unit': 'Unit\nchange',
                      'mirror': 'Backup\ncopy'},
           'classes': {'none': 'No change, benign updates', 'covered': 'Breaks covered by a condition',
                       'outside': 'Outside the guarantee'},
           'roles': {'none': 'No shared memory', 'unmaintained': 'Shared, not maintained: existing approaches',
                     'maintained': 'Shared and maintained'},
           'names': {'middle': 'No memory',
                     'traj-global': 'Example retrieval (agent memory)',
                     'metric-global-schema': 'Invalidate on schema change (metric layers)',
                     'metric-global-revoke': 'Invalidate on every write (relearns)',
                     'metric-global-snap': 'MAVRA (ours)'},
           'y': 'Accuracy (%)', 'stale': 'stale definition in ≥25% of tasks'},
    'zh': {'groups': {'holdout': '留出题', 'benign': '正常更新\n（4 种）', 'status': '状态\n变更行',
                      'revision': '多版本\n更正', 'dupload': '重复\n加载', 'dimhist': '缓慢\n变化维',
                      'latekey': '日期键\n格式', 'covered': '全部覆盖\n的破坏', 'unit': '金额\n单位',
                      'mirror': '备份\n副本'},
           'classes': {'none': '无变化与正常更新', 'covered': '条件覆盖的破坏性变化', 'outside': '保证范围之外'},
           'roles': {'none': '不共享', 'unmaintained': '共享但不维护（现有做法）', 'maintained': '共享并维护'},
           'names': {'middle': '无记忆', 'traj-global': '示例检索（智能体记忆）',
                     'metric-global-schema': '模式变更时失效（指标层的保护手段）',
                     'metric-global-revoke': '每次写入即失效（重新学习）', 'metric-global-snap': 'MAVRA（本文）'},
           'y': '正确率（%）', 'stale': '≥25% 的题用了过期定义'},
}

# Geometry: data units along x; one group is len(METHODS) bars of width BW, and the pooled
# summary of the covered breaks, the group the text compares, has wider bars with printed values.
BW, SUMMARY_BW = 1.0, 1.7
GAP_IN, GAP_CLASS = 2.2, 4.4      # between groups of one class / between classes
LEFT, RIGHT, BOTTOM, TOP = .048, .005, .235, .755   # axes box, figure fractions
LEGEND_GAP, SWATCH = 4.5, 2.6                       # mm between legend blocks; swatch side


def legend(fig, lang, T):
    """Legend in blocks by role: a muted title with a rule, then one entry per method, stacked."""
    renderer = fig.canvas.get_renderer()
    fx, fy = 1 / W, 1 / H                           # figure fraction per mm

    def width_mm(s, size):
        t = fig.text(0, 0, s, fontsize=size)
        w = t.get_window_extent(renderer).width / fig.bbox.width * W
        t.remove()
        return w

    blocks = []                                     # (title, [(swatch spec, label, bold)], width mm)
    for role, modes in ROLES:
        entries = [((style.method(m, lang)[1], None), T['names'][m], m == OURS) for m in modes]
        w = max([width_mm(T['roles'][role], mplstyle.SMALL)]
                + [SWATCH + 1.2 + width_mm(label, mplstyle.LABEL) for _, label, _ in entries])
        blocks.append((T['roles'][role], entries, w))
    blocks.append(('', [(('#E9E7E2', RED), T['stale'], False)], SWATCH + 1.2 + width_mm(T['stale'], mplstyle.LABEL)))
    total = sum(w for *_, w in blocks) + LEGEND_GAP * (len(blocks) - 1)
    if total > W - 2:
        raise SystemExit(f'{NAME}: legend is {total:.1f} mm wide, the figure {W} mm')
    x = (W - total) / 2
    y_title, y_rule, rows = H - 1.2, H - 4.4, (H - 7.2, H - 10.6)
    for title, entries, w in blocks:
        if title:
            fig.text(x * fx, y_title * fy, title, fontsize=mplstyle.SMALL, color=MUTED, ha='left', va='top')
            fig.add_artist(Line2D([x * fx, (x + w) * fx], [y_rule * fy] * 2, color=MUTED, lw=.4,
                                  transform=fig.transFigure))
        for ((face, edge), label, bold), y in zip(entries, rows):
            fig.patches.append(Rectangle((x * fx, (y - SWATCH / 2) * fy), SWATCH * fx, SWATCH * fy,
                                         facecolor=face, edgecolor=edge or 'none', hatch='////' if edge else None,
                                         lw=0, transform=fig.transFigure, figure=fig))
            fig.text((x + SWATCH + 1.2) * fx, y * fy, label, fontsize=mplstyle.LABEL,
                     color=ACC_DK if bold else INK, fontweight='bold' if bold else 'normal', ha='left', va='center')
        x += w + LEGEND_GAP


def load():
    """Per (method, group): accuracy, 95% interval (all in %), stale flag."""
    methods = json.loads(STATS.read_text(encoding='utf-8'))['methods']
    results = json.loads(RESULTS.read_text(encoding='utf-8'))
    numbers, intervals = style.macros('numbers'), style.macros('scen-ds')
    models = sorted({key.split('|')[0] for key in results['accuracy']})
    rnd = random.Random(SEED)
    cells = {}
    for mode in METHODS:
        runs = methods[mode]['runs']
        for phase, *_ in PHASES:
            k = sum(r['acc'].get(phase, [0, 0])[0] for r in runs)
            n = sum(r['acc'].get(phase, [0, 0])[1] for r in runs)
            # The same pooled accuracy from the other archive (tools/paper-results.py).
            k2, n2 = (sum(x) for x in zip(*(results['accuracy'].get(f'{m}|{mode}|{phase}', (0, 0)) for m in models)))
            style.agree(f'{mode}/{phase} accuracy', f'{k}/{n}', f'{k2}/{n2}')
            name = f'ScenAcc{KEY[mode]}{phase.capitalize()}'
            if name in numbers and n:
                style.agree(name, f'{100 * k / n:.0f}', numbers[name])
        for group, phases, _, macro in GROUPS:
            acc = scen_stats.rate(runs, phases)
            if macro:
                printed = methods[mode][macro.lower()]
                style.agree(f'{mode}/{group} accuracy', f'{acc:.6f}', f'{printed["acc"]:.6f}')
                lo, hi = printed['ci95']
                for suffix, v in (('', acc), ('Lo', lo), ('Hi', hi)):
                    style.agree(f'Ds{KEY[mode]}{macro}{suffix}', f'{100 * v:.0f}',
                                intervals[f'Ds{KEY[mode]}{macro}{suffix}'])
            else:
                lo, hi = scen_stats.ci(scen_stats.boot(runs, phases, REPS, rnd))
            n = sum(r['acc'].get(p, [0, 0])[1] for r in runs for p in phases)
            stale = sum(r['stale'].get(p, 0) for r in runs for p in phases)
            cells[mode, group] = (100 * acc, 100 * lo, 100 * hi, n > 0 and stale / n >= STALE)
    return cells


def bar_width(group):
    return SUMMARY_BW if group == 'covered' else BW


def positions():
    """Left x and width of every group, and the x span of every class."""
    xs, widths, spans, x, previous = {}, {}, {}, 0.0, None
    for group, _, cls, _ in GROUPS:
        if previous is not None:
            x += GAP_IN if cls == previous else GAP_CLASS
        width = len(METHODS) * bar_width(group)
        xs[group], widths[group] = x, width
        spans.setdefault(cls, [x, x])[1] = x + width
        x += width
        previous = cls
    return xs, widths, spans


def figure(lang):
    cells, T = load(), TEXT[lang]
    plt.rcParams['hatch.linewidth'] = .6
    xs, widths, spans = positions()
    fig = mplstyle.figure(W, H)
    ax = fig.add_axes([LEFT, BOTTOM, 1 - LEFT - RIGHT, TOP - BOTTOM])
    below = transforms.blended_transform_factory(ax.transData, ax.transAxes)

    for group, _, cls, _ in GROUPS:
        x0, width, bw = xs[group], widths[group], bar_width(group)
        if group in POOLED:
            ax.axvspan(x0 - GAP_IN / 2 + .3, x0 + width + GAP_IN / 2 - .3, color=FIELD, lw=0, zorder=0)
        for i, mode in enumerate(METHODS):
            acc, lo, hi, stale = cells[mode, group]
            _, color = style.method(mode, lang)
            bx = x0 + i * bw
            ax.bar(bx, acc, width=bw * .9, align='edge', color=color, lw=0, zorder=3)
            if stale:
                ax.bar(bx, acc, width=bw * .9, align='edge', facecolor='none', edgecolor=RED, hatch='///',
                       lw=0, zorder=4)
            if hi > lo + .05:
                ax.plot([bx + bw * .45] * 2, [lo, hi], color=INK, lw=.5, solid_capstyle='butt', zorder=5)
            if group == 'covered':
                ax.text(bx + bw * .45, hi + 1.5, f'{acc:.0f}', ha='center', va='bottom',
                        fontsize=mplstyle.SMALL, color=ACC_DK if mode == OURS else INK,
                        fontweight='bold' if mode == OURS else 'normal', zorder=6)

    last = GROUPS[-1][0]
    ax.set_xlim(-GAP_IN / 2, xs[last] + widths[last] + GAP_IN / 2)
    ax.set_ylim(0, 104)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(['0', '25', '50', '75', '100'])
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.spines['bottom'].set_visible(False)
    ax.set_xticks([xs[g] + widths[g] / 2 for g, *_ in GROUPS])
    ax.set_xticklabels([T['groups'][g] for g, *_ in GROUPS], linespacing=.95)
    ax.tick_params(axis='x', length=0, pad=2.5)
    fig.text(.003, TOP + .015, T['y'], color=MUTED, fontsize=mplstyle.LABEL, ha='left', va='bottom')

    # The second level of the axis: one bracket per class.
    for cls, (x0, x1) in spans.items():
        ax.plot([x0 + .2, x0 + .2, x1 - .2, x1 - .2], [-.215, -.235, -.235, -.215], color=MUTED, lw=.5,
                transform=below, clip_on=False, solid_capstyle='butt')
        ax.text((x0 + x1) / 2, -.265, T['classes'][cls], transform=below, ha='center', va='top',
                fontsize=mplstyle.LABEL, color=MUTED)

    fig.canvas.draw()
    legend(fig, lang, T)

    # Every group label must fit between its neighbours.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    mm_per_px = W / fig.bbox.width
    mm_per_unit = (1 - LEFT - RIGHT) * W / (ax.get_xlim()[1] - ax.get_xlim()[0])
    tight = [f'{t.get_text()!r} {need:.1f} mm in {room:.1f} mm'
             for t, (g, *_) in zip(ax.get_xticklabels(), GROUPS)
             for room in [(widths[g] + GAP_IN) * mm_per_unit]
             for need in [t.get_window_extent(renderer).width * mm_per_px] if need > room - .4]
    if tight:
        raise SystemExit(f'{NAME}: group labels too wide: ' + '; '.join(tight))
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
