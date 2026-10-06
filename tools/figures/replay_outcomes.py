"""Figure: library replay, outcome of every scored question per method.

One 100% bar per method splits its questions into correct, wrong, and
invalidated (correctly or falsely); maintenance database time sits at the
right. All methods use the agent's own SQL as the G8 reference on the
learning snapshot; the last row repeats MAVRA with G8 on current data. Counts are over the questions every row
answers (task_level_common). Data: exp/2026-10-02-cache-baseline-tpcds/replay-stats.json, the
archive tools/review-results.py turns into the \\Rp* macros; every count and
time is checked against those macros.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import Scale, measure  # noqa: E402
import style  # noqa: E402
from style import ACC_PALE, GRID, INK, MUTED, RED, WHITE  # noqa: E402

NAME = 'replay-outcomes'
W, H = style.COLUMN, 35.4
DATA = style.ROOT / 'exp/2026-10-02-cache-baseline-tpcds/replay-stats.json'

# (replay group, method key in style.METHODS, macro key, footnote mark)
ROWS = [('schema/snapshot', 'metric-global-schema', 'Schema', ''),
        ('tabletest/snapshot', 'tabletest', 'Table', ''),
        ('revoke/snapshot', 'metric-global-revoke', 'Revoke', 'a'),
        ('definition/snapshot', 'definition', 'Def', ''),
        ('definition-cache/snapshot', 'definition-cache', 'Cache', ''),
        ('condition/snapshot', 'condition', 'Cond', ''),
        ('condition/example', 'condition-current', 'Cur', 'b')]
# (field, macro suffix, fill, text color)
OUTCOMES = [('correct', 'Correct', '#5B5853', WHITE),
            ('served_wrong', 'Wrong', RED, WHITE),
            ('unavailable_needed', 'Needed', '#B4B0A9', INK),
            ('unavailable_unneeded', 'Unneeded', '#E2DFD9', INK)]
TEXT = {
    'en': {'outcomes': ('Correct', 'Wrong', 'Correct invalidation', 'False invalidation'),
           'db': 'Maint. DB s'},
    'zh': {'outcomes': ('答对', '答错', '正确失效', '误失效'),
           'db': '维护 DB 秒'},
}
LABEL, NUM, TICK = 6.5, 6.0, 6.0       # font sizes, pt (acmart \scriptsize is 6)


def _int(n):
    return f'{n:,}'.replace(',', '{,}')


def load():
    stats = json.loads(DATA.read_text(encoding='utf-8'))
    printed = style.macros('review')
    rows = []
    for group, key, macro, mark in ROWS:
        cell = stats['task_level_common'][group]
        counts = [cell[field] for field, *_ in OUTCOMES]
        if sum(counts) != cell['n']:
            raise SystemExit(f'{group}: outcomes add up to {sum(counts)}, not {cell["n"]}')
        for (field, suffix, *_), count in zip(OUTCOMES, counts):
            style.agree(f'Rp{macro}{suffix}', _int(count), printed[f'Rp{macro}{suffix}'])
        db = stats['maintenance_db_s'][group]['total']
        style.agree(f'Rp{macro}DB', f'{db:.1f}', printed[f'Rp{macro}DB'])
        style.agree(f'Rp{macro}N', _int(cell['n']), printed[f'Rp{macro}N'])
        rows.append((key, mark, counts, db))
    return rows


def draw(s, lang):
    rows, T, text = load(), TEXT[lang], s.text

    # Legend: one swatch per outcome, wrapped to the figure width.
    x, y = 0, 2.6
    for (_, _, fill, _), label in zip(OUTCOMES, T['outcomes']):
        width = 2.2 + measure(label, LABEL) + 2.6
        if x + width > W:
            x, y = 0, y + 3.6
        s.rect(x, y - 1.9, 1.6, 1.6, fill, None, r=.2)
        text(x + 2.2, y - .35, label, LABEL, INK)
        x += width
    top = y + 3.0

    labels = []
    for key, mark, _, _ in rows:
        label, color = style.method(key, lang)
        labels.append((label + (f'${{}}^{mark}$' if mark else ''), color))
    left = 2.4 + max(measure(label, LABEL) for label, _ in labels) + 1.4
    right = W - 11.5
    bar = Scale(0, 1, left, right)
    pitch, height = 3.6, 2.6
    bottom = top + pitch * len(rows)

    text(W, top - .8, T['db'], LABEL - .5, MUTED, align='right')
    for v in (.25, .5, .75):
        s.line(bar(v), top, bar(v), bottom, GRID, .14)

    for i, ((key, mark, counts, db), (label, color)) in enumerate(zip(rows, labels)):
        yc = top + pitch * (i + .5)
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
    for v in (0, .25, .5, .75, 1):
        s.line(bar(v), bottom, bar(v), bottom + .7, MUTED, .16)
        align = 'left' if v == 0 else 'right' if v == 1 else 'center'
        dx = -.3 if v == 0 else .3 if v == 1 else 0
        text(bar(v) + dx, bottom + 3.1, f'{round(100 * v)}%', TICK, MUTED, align=align)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
