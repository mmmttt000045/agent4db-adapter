"""Figure: library replay, outcome of every scored question per method.

Two panels share the legend, the bar scale, and the maintenance-time column.
The upper panel replays the libraries learned by three LLMs on the synthetic
fixture; the lower one replays the TPC-DS library derived from the query
templates on TPC-DS SF1. One 100% bar per method splits its questions into
correct, wrong, and invalidated (correctly or falsely); maintenance database
time sits at the right. All methods use the agent's own SQL as the G8
reference, compared as of learning time; the last row of each panel repeats
MAVRA with G8 on current data. Counts are over the questions every row
answers (task_level_common). Data: exp/2026-10-02-cache-baseline-tpcds/
replay-stats.json and tpcds-replay-stats.json, the archives that
tools/review-results.py turns into the \\Rp* and \\Tr* macros; every count,
time, and panel-title number is checked against those macros.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import Scale, measure  # noqa: E402
import style  # noqa: E402
from style import ACC_PALE, GRID, INK, MUTED, RED, WHITE  # noqa: E402

NAME = 'replay-outcomes'
W, H = style.COLUMN, 64.0
EXP = style.ROOT / 'exp/2026-10-02-cache-baseline-tpcds'

# (replay group, method key in style.METHODS, macro key, footnote mark)
ROWS = [('schema/snapshot', 'metric-global-schema', 'Schema', ''),
        ('tabletest/snapshot', 'tabletest', 'Table', ''),
        ('revoke/snapshot', 'metric-global-revoke', 'Revoke', 'a'),
        ('definition/snapshot', 'definition', 'Def', ''),
        ('definition-cache/snapshot', 'definition-cache', 'Cache', ''),
        ('condition/snapshot', 'condition', 'Cond', ''),
        ('condition/example', 'condition-current', 'Cur', 'b')]
# The TPC-DS replay runs the methods whose outcome can differ from MAVRA's: the
# definition-level baseline and the check-result cache give identical answers.
TPCDS_ROWS = [r for r in ROWS if r[0] not in ('definition/snapshot', 'definition-cache/snapshot')]
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
                      'TPC-DS SF1: {defs} template-derived definitions, {n} questions')},
    'zh': {'outcomes': ('答对', '答错', '正确失效', '误失效'),
           'db': '维护 DB 秒',
           'titles': ('学到的定义库：{libs} 个库，每种方法 {n} 题',
                      'TPC-DS SF1：{defs} 个模板导出的定义，{n} 题')},
}
LABEL, NUM, TICK, TITLE = 6.5, 6.0, 6.0, 7.0   # font sizes, pt (acmart \scriptsize 6, \footnotesize 7)


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
        n = rows[0][2]
        numbers = {'n': f'{sum(n):,}'}
        if prefix == 'Rp':
            style.agree('RpLibs', str(stats['libraries']), printed['RpLibs'])
            numbers['libs'] = stats['libraries']
        else:
            library = json.loads((EXP / 'tpcds-library.json').read_text(encoding='utf-8'))
            defs = len(library['metric_report']['entries'])
            style.agree('TrDefs', str(defs), printed['TrDefs'])
            numbers['defs'] = defs
        panels.append((numbers, rows))
    return panels


def draw(s, lang):
    panels, T, text = load(), TEXT[lang], s.text

    # Legend: one swatch per outcome, wrapped to the figure width.
    x, y = 0, 2.6
    for (_, _, fill, _), label in zip(OUTCOMES, T['outcomes']):
        width = 2.2 + measure(label, LABEL) + 2.6
        if x + width > W:
            x, y = 0, y + 3.6
        s.rect(x, y - 1.9, 1.6, 1.6, fill, None, r=.2)
        text(x + 2.2, y - .35, label, LABEL, INK)
        x += width
    y += 2.2

    def label_of(key, mark):
        label, color = style.method(key, lang)
        return label + (f'${{}}^{mark}$' if mark else ''), color
    left = 2.4 + max(measure(label_of(key, mark)[0], LABEL) for _, key, _, mark in ROWS) + 1.4
    right = W - 11.5
    bar = Scale(0, 1, left, right)
    pitch, height = 3.6, 2.6

    text(W, y + 2.6, T['db'], LABEL - .5, MUTED, align='right')
    for k, ((numbers, rows), title) in enumerate(zip(panels, T['titles'])):
        text(0, y + 2.6, title.format(**numbers), TITLE, INK, 'bold', width=right - 1.0)
        top = y + 4.2
        bottom = top + pitch * len(rows)
        for v in (.25, .5, .75):
            s.line(bar(v), top, bar(v), bottom, GRID, .14)
        for i, (key, mark, counts, db) in enumerate(rows):
            yc = top + pitch * (i + .5)
            label, color = label_of(key, mark)
            if key == 'condition':
                s.rect(0, yc - pitch / 2, W, pitch, ACC_PALE, None)
            s.rect(0, yc - .8, 1.6, 1.6, color, None, r=.2)
            text(2.4, yc + .8, label, LABEL, INK)
            total, done = sum(counts), 0
            for (_, _, fill, ink), count in zip(OUTCOMES, counts):
                if count:
                    x0, x1 = bar(done / total), bar((done + count) / total)
                    s.rect(x0, yc - height / 2, x1 - x0, height, fill, WHITE, .12)
                    number = f'{count:,}'
                    if measure(number, NUM) + .35 <= x1 - x0:
                        text((x0 + x1) / 2, yc + .75, number, NUM, ink, align='center')
                done += count
            text(W, yc + .8, f'{db:,.1f}', NUM, INK, align='right')
        s.line(left, bottom, right, bottom, MUTED, .16)
        if k == len(panels) - 1:
            for v in (0, .25, .5, .75, 1):
                s.line(bar(v), bottom, bar(v), bottom + .7, MUTED, .16)
                align = 'left' if v == 0 else 'right' if v == 1 else 'center'
                dx = -.3 if v == 0 else .3 if v == 1 else 0
                text(bar(v) + dx, bottom + 3.1, f'{round(100 * v)}%', TICK, MUTED, align=align)
        y = bottom + 2.4


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
