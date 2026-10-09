"""Figure: accuracy of the user agent by data change, as a result matrix.

One row per method of the end-to-end study, one column per setting in the
order of tools/paper-results.py, grouped under the header by what the change
does (no change, benign updates, breaks covered by a condition, changes
outside the guarantee: a unit change and an ambiguous fix). Each cell prints the accuracy over the three independent runs,
shades it on one blue scale, and adds the range of the three runs underneath
when the runs differ; a red frame marks a cell in which at least 25% of the
tasks used a stale definition. The right block repeats, per method, the
accuracy over the covered breaks with its 95% interval and, for the methods
that keep definitions, invalidations and published repairs per run. Data:
exp/2026-10-02-scenarios-ds/scen-stats.json (per-run counts written by
tools/scen-stats.py), cross-checked against paper-results.json and against
every value the text prints (\\ScenAcc* in gen/numbers.tex, \\Ds* in
gen/scen-ds.tex).
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.colors import LinearSegmentedColormap, to_rgb  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import ACC_DK, FACE, INK, MUTED, RED, RULE, WHITE  # noqa: E402

NAME = 'scenario-changes'
W = style.TEXTWIDTH
STATS = style.ROOT / 'exp/2026-10-02-scenarios-ds/scen-stats.json'
RESULTS = style.ROOT / 'exp/2026-10-02-scenarios-ds/paper-results.json'
STALE = .25                      # share of tasks that used a stale definition

_spec = importlib.util.spec_from_file_location('paper_results', style.ROOT / 'tools/paper-results.py')
paper_results = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paper_results)
PHASES = paper_results.PHASES

# Rows in the order of Table 2; a wider gap separates what is shared.
ROWS = [['middle'], ['traj-global', 'traj-verify'],
        ['metric-global-schema', 'metric-global-revoke', 'metric-global-def', 'metric-global-snap',
         'metric-global-exref', 'metric-global']]
OURS = 'metric-global-snap'
MAINTAINERS = {'metric-global-revoke', 'metric-global-def', 'metric-global-snap', 'metric-global-exref',
               'metric-global'}
# Macro keys of tools/scen-stats.py and tools/paper-results.py: \Ds<key>*, \ScenAcc<key>*.
KEY = {'middle': 'NoShare', 'traj-global': 'Traj', 'traj-verify': 'TrajVerify',
       'metric-global-schema': 'Schema', 'metric-global-revoke': 'Revoke', 'metric-global-def': 'Def',
       'metric-global-snap': 'Cond', 'metric-global-exref': 'CondCur', 'metric-global': 'CondGold'}
# Header groups: what the change does to a learned definition.
GROUP = {'holdout': 'none', 'append': 'benign', 'backfill': 'benign', 'correct': 'benign',
         'addcol': 'benign', 'status': 'covered', 'revision': 'covered', 'dupload': 'covered',
         'dimhist': 'covered', 'latekey': 'covered', 'unit': 'outside', 'mirror': 'outside'}
TEXT = {
    'en': {'groups': {'none': 'None', 'benign': 'Benign updates', 'covered': 'Breaks covered by a condition',
                      'outside': 'Outside the\nguarantee', 'run': 'Per run'},
           'settings': {'holdout': 'Held-out', 'append': 'Append', 'backfill': 'Late\narriving',
                        'correct': 'In-place\nfix', 'addcol': 'New\ncolumn', 'status': 'Status\nrows',
                        'revision': 'Restated\nsales', 'dupload': 'Duplicate\nload', 'dimhist': 'SCD\nType 2',
                        'latekey': 'Date-key\nformat', 'unit': 'Unit\nchange', 'mirror': 'Backup\ncopy',
                        'covered': 'All covered\nbreaks', 'inval': 'Invalidated', 'repair': 'Repaired'},
           'rows': {'middle': 'No memory', 'traj-global': 'Example retrieval',
                    'traj-verify': 'Example retrieval\n+ self-verification',
                    'metric-global-schema': 'Invalidate on\nschema change',
                    'metric-global-revoke': 'Invalidate on\nevery write',
                    'metric-global-def': 'Full recheck\nper definition', 'metric-global-snap': 'MAVRA (ours)',
                    'metric-global-exref': 'MAVRA, regression\non current data',
                    'metric-global': 'MAVRA, gold-SQL\nreference'},
           'key_cell': 'accuracy;\nrange of 3 runs', 'key_stale': 'stale definition\nin ≥25% of tasks'},
    'zh': {'groups': {'none': '无变化', 'benign': '正常更新', 'covered': '条件覆盖的破坏性变化',
                      'outside': '保证范围之外', 'run': '每次运行'},
           'settings': {'holdout': '留出', 'append': '正常\n追加', 'backfill': '迟到\n事实',
                        'correct': '原地\n更正', 'addcol': '新增\n无关列', 'status': '状态\n变更行',
                        'revision': '多版本\n更正', 'dupload': '重复\n加载', 'dimhist': '缓慢\n变化维',
                        'latekey': '日期键\n格式', 'unit': '金额\n单位', 'mirror': '备份\n副本',
                        'covered': '全部覆盖\n的破坏', 'inval': '失效', 'repair': '修复'},
           'rows': {'middle': '无记忆', 'traj-global': '示例检索', 'traj-verify': '示例检索\n+ 自行核验',
                    'metric-global-schema': '模式变更时失效', 'metric-global-revoke': '每次写入即失效',
                    'metric-global-def': '整定义重查', 'metric-global-snap': 'MAVRA（本文）',
                    'metric-global-exref': 'MAVRA，回归\n测试用当前数据',
                    'metric-global': 'MAVRA，标准\n答案作参照'},
           'key_cell': '正确率；\n3 次运行的范围', 'key_stale': '≥25% 的题用\n了过期定义'},
}

# Geometry, mm.
LABEL_W = 23.2                   # row labels
CELL_W, CELL_H = 9.2, 5.4
GAP_IN, GAP_GROUP = .4, 1.4       # between columns of one group / between groups
GAP_ROWS, GAP_SET = .4, 1.3       # between rows / between the sets of rows
RIGHT_GAP = 2.6                   # before the right block
COV_W, INV_W, REP_W = 11.0, 11.0, 9.4
HEAD1, HEAD2 = 6.4, 6.2           # group header, setting header
SCALE = LinearSegmentedColormap.from_list('acc', ['#F7F9FC', '#D3E2F4', '#8DB3E2', '#3D77C1'])


def load():
    """Per (method, phase): run accuracies, pooled accuracy, stale flag; per method: summary values."""
    methods = json.loads(STATS.read_text(encoding='utf-8'))['methods']
    results = json.loads(RESULTS.read_text(encoding='utf-8'))
    numbers, intervals = style.macros('numbers'), style.macros('scen-ds')
    models = sorted({key.split('|')[0] for key in results['accuracy']})
    cells, summary = {}, {}
    for mode in [m for rows in ROWS for m in rows]:
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
        acc, lo, hi = (f'{100 * v:.0f}' for v in (covered['acc'], *covered['ci95']))
        for suffix, v in (('', acc), ('Lo', lo), ('Hi', hi)):
            style.agree(f'Ds{KEY[mode]}Modeled{suffix}', v, intervals[f'Ds{KEY[mode]}Modeled{suffix}'])
        row = methods[mode]
        rev, rep = f'{row["revoked_per_cell"]:.1f}', f'{row["repaired_per_cell"]:.1f}'
        style.agree(f'Ds{KEY[mode]}Revoked', rev, intervals[f'Ds{KEY[mode]}Revoked'])
        style.agree(f'Ds{KEY[mode]}Repaired', rep, intervals[f'Ds{KEY[mode]}Repaired'])
        summary[mode] = (float(acc), f'{lo}–{hi}' if lo != hi else '', rev, rep)
    return cells, summary


def columns():
    """x of every setting column and of the right block, with the group spans for the header."""
    xs, spans, x = {}, [], LABEL_W
    for i, (phase, *_) in enumerate(PHASES):
        group = GROUP[phase]
        if i:
            x += GAP_IN if GROUP[PHASES[i - 1][0]] == group else GAP_GROUP
        xs[phase] = x
        if spans and spans[-1][0] == group:
            spans[-1][2] = x + CELL_W
        else:
            spans.append([group, x, x + CELL_W])
        x += CELL_W
    x += RIGHT_GAP
    xs['covered'] = x
    x += COV_W + GAP_GROUP
    xs['inval'] = x
    xs['repair'] = x + INV_W + GAP_IN
    spans.append(['run', xs['inval'], xs['repair'] + REP_W])
    return xs, spans, xs['repair'] + REP_W


def ink_on(value):
    r, g, b = to_rgb(SCALE(value / 100))
    return WHITE if .299 * r + .587 * g + .114 * b < .55 else INK


def figure(lang):
    cells, summary = load()
    T = TEXT[lang]
    xs, spans, right = columns()
    if right > W + .01:
        raise SystemExit(f'{NAME}: the matrix is {right:.1f} mm wide, the page {W} mm')
    top = HEAD1 + HEAD2
    ys, y = {}, top
    for s, rows in enumerate(ROWS):
        for r, mode in enumerate(rows):
            if s or r:
                y += GAP_SET if r == 0 else GAP_ROWS
            ys[mode] = y
            y += CELL_H
    H = y + .6
    fig = mplstyle.figure(W, H)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis('off')

    def text(x, y, s, **kw):
        kw.setdefault('fontsize', mplstyle.LABEL)
        kw.setdefault('color', INK)
        kw.setdefault('linespacing', .95)
        return ax.text(x, y, s, **kw)

    widths = {p: CELL_W for p, *_ in PHASES}
    widths.update(covered=COV_W, inval=INV_W, repair=REP_W)

    # Header: groups with a rule under each span, then one label per column.
    fitted = []                                   # (header label, mm available)
    for group, x0, x1 in spans:
        fitted.append((text((x0 + x1) / 2, HEAD1 - 1.3, T['groups'][group], ha='center', va='bottom',
                            fontweight='bold'), x1 - x0))
        ax.plot([x0 + .2, x1 - .2], [HEAD1 - .55] * 2, color=MUTED, lw=.5, solid_capstyle='butt')
    for key, x in xs.items():
        fitted.append((text(x + widths[key] / 2, top - .9, T['settings'][key], ha='center', va='bottom',
                            fontsize=mplstyle.TICK), widths[key]))

    # Key, in the free corner above the row labels: one cell as it reads, one stale cell.
    for y0, stale, caption in ((.3, False, T['key_cell']), (6.1, True, T['key_stale'])):
        ax.add_patch(Rectangle((.3, y0), 6.6, 5.0, facecolor=SCALE(.93), lw=0))
        if stale:
            ax.add_patch(Rectangle((.75, y0 + .45), 5.7, 4.1, facecolor='none', edgecolor=RED, lw=1.0))
        ink = ink_on(93)
        text(3.6, y0 + 1.55, '93' if not stale else '50', ha='center', va='center', color=ink)
        if not stale:
            text(3.6, y0 + 3.75, '89–100', ha='center', va='center', fontsize=mplstyle.TICK, color=ink)
        text(7.7, y0 + 2.5, caption, va='center', fontsize=mplstyle.TICK, color=MUTED)

    for mode, y in ys.items():
        ours = mode == OURS
        text(LABEL_W - 1.2, y + CELL_H / 2, T['rows'][mode], ha='right', va='center',
             fontweight='bold' if ours else 'normal', color=ACC_DK if ours else INK)
        weight = 'bold' if ours else 'normal'
        for phase, *_ in PHASES:
            runs, mean, stale = cells[mode, phase]
            x = xs[phase]
            ax.add_patch(Rectangle((x, y), CELL_W, CELL_H, facecolor=SCALE(mean / 100), lw=0))
            if stale:
                ax.add_patch(Rectangle((x + .45, y + .45), CELL_W - .9, CELL_H - .9, facecolor='none',
                                       edgecolor=RED, lw=1.0))
            ink = ink_on(mean)
            spread = len(runs) > 1 and max(runs) - min(runs) > .5
            cy = y + CELL_H / 2 - (.95 if spread else 0)
            text(x + CELL_W / 2, cy, f'{mean:.0f}', ha='center', va='center', color=ink, fontweight=weight)
            if spread:
                text(x + CELL_W / 2, y + CELL_H / 2 + 1.25, f'{min(runs):.0f}–{max(runs):.0f}', ha='center',
                     va='center', fontsize=mplstyle.TICK, color=ink, alpha=.85)
        acc, ci, rev, rep = summary[mode]
        x = xs['covered']
        ax.add_patch(Rectangle((x, y), COV_W, CELL_H, facecolor=SCALE(acc / 100), lw=0))
        ink = ink_on(acc)
        text(x + COV_W / 2, y + CELL_H / 2 - (.95 if ci else 0), f'{acc:.0f}', ha='center', va='center',
             color=ink, fontweight=weight)
        if ci:
            text(x + COV_W / 2, y + CELL_H / 2 + 1.25, ci, ha='center', va='center', fontsize=mplstyle.TICK,
                 color=ink, alpha=.85)
        keeps = mode in MAINTAINERS
        for key, value, width in (('inval', rev, INV_W), ('repair', rep, REP_W)):
            x = xs[key]
            ax.add_patch(Rectangle((x, y), width, CELL_H, facecolor=FACE, edgecolor=RULE, lw=.3))
            shown = ('0' if float(value) == 0 else value) if keeps or float(value) else '–'
            text(x + width / 2, y + CELL_H / 2, shown, ha='center', va='center',
                 color=INK if keeps else MUTED, fontweight=weight)
    # Outline the row of the method this paper proposes.
    y = ys[OURS]
    ax.add_patch(Rectangle((xs['holdout'] - .15, y - .15), right - xs['holdout'] + .3, CELL_H + .3,
                           facecolor='none', edgecolor=ACC_DK, lw=.7, zorder=5))

    # Every header label must fit its column or group; a wider one would run into the next.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    mm_per_px = W / fig.bbox.width
    tight = [f'{t.get_text()!r} {need:.1f} mm in {room:.1f} mm' for t, room in fitted
             for need in [t.get_window_extent(renderer).width * mm_per_px] if need > room + .6]
    if tight:
        raise SystemExit(f'{NAME}: header labels too wide: ' + '; '.join(tight))
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
