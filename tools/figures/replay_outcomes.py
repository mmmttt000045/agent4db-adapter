"""Figure: library replay, outcome of every scored question per method.

Two panels share the legend, the bar scale, and the maintenance-time column.
The upper panel replays the libraries learned by three LLMs on the synthetic
fixture; the lower one replays the TPC-DS library derived from the query
templates on TPC-DS SF1. One 100% bar per method splits its questions into
correct, wrong, and invalidated (correctly or falsely); maintenance database
time sits at the right. All methods use the agent's own SQL as the G8
reference, compared as of learning time; the last row of each panel repeats
MAVRA with the regression test on current data. Counts are over the questions every row
answers (task_level_common). Data: exp/2026-10-02-cache-baseline-tpcds/
replay-stats.json and tpcds-replay-stats.json, the archives that
tools/review-results.py turns into the \\Rp* and \\Tr* macros; every count,
time, and panel-title number is checked against those macros.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib import transforms  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import ACC_PALE, INK, MUTED, RED, WHITE  # noqa: E402

NAME = 'replay-outcomes'
W, H = style.COLUMN, 66.0
EXP = style.ROOT / 'exp/2026-10-02-cache-baseline-tpcds'

# (replay group, method key in style.METHODS, macro key, footnote mark)
# Invalidation on every write (answers nothing without relearning) and the query
# cache (identical to the full recheck) are replayed but not drawn; see \Rp*.
ROWS = [('schema/snapshot', 'metric-global-schema', 'Schema', ''),
        ('tabletest/snapshot', 'tabletest', 'Table', ''),
        ('definition/snapshot', 'definition', 'Def', ''),
        ('condition/snapshot', 'condition', 'Cond', ''),
        ('condition/example', 'condition-current', 'Cur', '')]
# The TPC-DS replay does not run the full recheck per definition.
TPCDS_ROWS = [r for r in ROWS if r[0] != 'definition/snapshot']
# (stats file, macro prefix, rows)
PANELS = [('replay-stats.json', 'Rp', ROWS), ('tpcds-replay-stats.json', 'Tr', TPCDS_ROWS)]
# (field, macro suffix, fill, text color)
OUTCOMES = [('correct', 'Correct', '#5B5853', WHITE),
            ('served_wrong', 'Wrong', RED, WHITE),
            ('unavailable_needed', 'Needed', '#B4B0A9', INK),
            ('unavailable_unneeded', 'Unneeded', '#E2DFD9', INK)]
TEXT = {
    'en': {'outcomes': ('Correct', 'Wrong', 'Correct invalidation', 'False invalidation'),
           'db': 'Maint. DB s',
           'titles': ('Learned libraries: {libs} libraries, {n} questions per method',
                      'TPC-DS SF1: {defs} admitted template-derived definitions, {n} questions')},
    'zh': {'outcomes': ('答对', '答错', '正确失效', '误失效'),
           'db': '维护 DB 秒',
           'titles': ('学到的定义库：{libs} 个库，每种方法 {n} 题',
                      'TPC-DS SF1：{defs} 个通过准入的模板导出定义，{n} 题')},
}
LEFT, RIGHT = .40, .85          # axes span in figure fractions: labels left, DB seconds right
# Labels too long for the margin are broken over two lines here.
LABELS = {'condition-current': {'en': 'MAVRA, regression\non current data', 'zh': 'MAVRA，回归测试\n用当前数据'}}


def _int(n):
    return f'{n:,}'.replace(',', '{,}')


def load():
    printed = style.macros('review')
    panels = []
    for file, prefix, spec in PANELS:
        stats = json.loads((EXP / file).read_text(encoding='utf-8'))
        rows = []
        for group, key, macro, mark in spec:
            cell = stats['task_level_common'][group]
            counts = [cell[field] for field, *_ in OUTCOMES]
            if sum(counts) != cell['n']:
                raise SystemExit(f'{file} {group}: outcomes add up to {sum(counts)}, not {cell["n"]}')
            for (field, suffix, *_), count in zip(OUTCOMES, counts):
                style.agree(f'{prefix}{macro}{suffix}', _int(count), printed[f'{prefix}{macro}{suffix}'])
            db = stats['maintenance_db_s'][group]['total']
            style.agree(f'{prefix}{macro}DB', f'{db:.1f}', printed[f'{prefix}{macro}DB'])
            style.agree(f'{prefix}{macro}N', _int(cell['n']), printed[f'{prefix}{macro}N'])
            rows.append((key, mark, counts, db))
        numbers = {'n': f'{sum(rows[0][2]):,}'}
        if prefix == 'Rp':
            style.agree('RpLibs', str(stats['libraries']), printed['RpLibs'])
            numbers['libs'] = stats['libraries']
        else:
            library = json.loads((EXP / 'tpcds-library.json').read_text(encoding='utf-8'))
            style.agree('TrDefs', str(len(library['metric_report']['entries'])), printed['TrDefs'])
            # The panel names the definitions that passed admission (\TrSeeded), the ones the replay
            # serves; the two that failed are counted by tools/review-results.py from the replay report.
            numbers['defs'] = printed['TrSeeded']
        panels.append((numbers, rows))
    return panels


def figure(lang):
    panels, T = load(), TEXT[lang]
    fig = mplstyle.figure(W, H)
    heights = [len(rows) for _, rows in panels]
    gs = GridSpec(len(panels), 1, figure=fig, height_ratios=heights, hspace=.55,
                  left=LEFT, right=RIGHT, top=.835, bottom=.085)
    fig.legend(handles=[Patch(facecolor=fill, label=label) for (_, _, fill, _), label in zip(OUTCOMES, T['outcomes'])],
               loc='upper left', bbox_to_anchor=(.0, 1.0), ncol=4, handlelength=1.0, handleheight=.9,
               columnspacing=.9)
    axes_width_pt = (RIGHT - LEFT) * W * 72 / 25.4
    fig.text(.995, .905, T['db'], ha='right', va='center', fontsize=mplstyle.TICK, color=MUTED)
    for k, (ax, (numbers, rows), title) in enumerate(zip([fig.add_subplot(g) for g in gs], panels, T['titles'])):
        n = len(rows)
        ys = list(range(n))[::-1]
        swatch = transforms.blended_transform_factory(ax.transAxes, ax.transData)
        for y, (key, mark, counts, db) in zip(ys, rows):
            label, color = style.method(key, lang)
            label = LABELS.get(key, {}).get(lang, label)
            if key == 'condition':
                ax.axhspan(y - .5, y + .5, xmin=-1.0, xmax=1.6, color=ACC_PALE, lw=0, zorder=0, clip_on=False)
            ax.scatter([-.015], [y], marker='s', s=11, color=color, transform=swatch, clip_on=False, zorder=3)
            mplstyle.label_with_mark(ax, -.035, y, label, mark, swatch)
            total, done = sum(counts), 0
            for (_, _, fill, ink), count in zip(OUTCOMES, counts):
                if count:
                    ax.barh(y, 100 * count / total, left=100 * done / total, height=.74, color=fill,
                            edgecolor=WHITE, lw=.35, zorder=2)
                    text = f'{count:,}'
                    if axes_width_pt * count / total >= 3.0 * len(text) + 1.2:
                        ax.text(100 * (done + count / 2) / total, y, text, ha='center', va='center',
                                fontsize=mplstyle.TICK, color=ink, zorder=4)
                done += count
            ax.text(1.17, y, f'{db:,.1f}', transform=swatch, ha='right', va='center',
                    fontsize=mplstyle.TICK, color=INK, clip_on=False)
        ax.set_title(title.format(**numbers), loc='left', pad=3, x=-.47)
        ax.set_xlim(0, 100)
        ax.set_ylim(-.5, n - .5)
        ax.set_yticks([])
        ax.spines['left'].set_visible(False)
        for v in (25, 50, 75):
            ax.axvline(v, color=style.GRID, lw=.4, zorder=1)
        if k == len(panels) - 1:
            ax.set_xticks([0, 25, 50, 75, 100])
            ax.set_xticklabels(['0%', '25%', '50%', '75%', '100%'])
        else:
            ax.set_xticks([])
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
