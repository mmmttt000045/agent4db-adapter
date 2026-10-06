"""Figure 4: accuracy of agent B by kind of change, one dot per method.

Rows are methods, labelled directly; columns are the five kinds of change on
a shared 0-100% axis; lines are the 95% cluster-bootstrap intervals over runs.
Data: exp/2026-10-02-scenarios-ds/scen-stats.json (written by
tools/scen-stats.py); every value is checked against the \\Ds* macros the
text prints from the same file.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import Scale, measure  # noqa: E402
import style  # noqa: E402
from style import ACC_PALE, GRID, INK, MUTED, RULE, WHITE  # noqa: E402

NAME = 'scenario-groups'
W, H = style.COLUMN, 43.5
DATA = style.ROOT / 'exp/2026-10-02-scenarios-ds/scen-stats.json'

ROWS = ['middle', 'traj-global', 'traj-verify', 'metric-global-noguard', 'metric-global-schema',
        'metric-global-revoke', 'metric-global-def', 'metric-global-exref', 'metric-global']
GROUPS = ['holdout', 'benign', 'modeled', 'mirror', 'unit']
TITLES = {
    'en': [('', 'Held-out'), ('', 'Benign'), ('Covered', 'breaking'), ('Backup', 'copy'),
           ('Unit', 'change')],
    'zh': [('', '留出'), ('', '正常'), ('条件覆盖', '的破坏'), ('备份', '副本'), ('金额', '单位')],
}
AXIS = {'en': 'Accuracy (%)', 'zh': '正确率（%）'}
# Macro keys of tools/scen-stats.py: \Ds<method><group>.
KEY = {'middle': 'NoShare', 'traj-global': 'Traj', 'traj-verify': 'TrajVerify',
       'metric-global-noguard': 'Noguard', 'metric-global-schema': 'Schema',
       'metric-global-revoke': 'Revoke', 'metric-global-def': 'Def', 'metric-global-exref': 'Cond',
       'metric-global': 'CondGold'}

LABEL, TICK, TITLE = 6.5, 6.0, 7.0     # font sizes, pt (acmart \scriptsize is 6, \footnotesize 7)


def load():
    stats = json.loads(DATA.read_text(encoding='utf-8'))['methods']
    printed = style.macros('scen-ds')
    rows = {}
    for m in ROWS:
        rows[m] = []
        for g in GROUPS:
            cell = stats[m][g]
            acc, (lo, hi) = cell['acc'], cell['ci95']
            name = f'Ds{KEY[m]}{g.capitalize()}'
            for suffix, v in (('', acc), ('Lo', lo), ('Hi', hi)):
                style.agree(name + suffix, f'{100 * v:.0f}', printed[name + suffix])
            rows[m].append((100 * acc, 100 * lo, 100 * hi))
    return rows


def draw(s, lang):
    rows = load()
    text = s.text
    labels = [style.method(m, lang) for m in ROWS]
    left = 2.4 + max(measure(label, LABEL) for label, _ in labels) + 1.0
    gap, right = 1.7, W - .9
    width = (right - left - gap * (len(GROUPS) - 1)) / len(GROUPS)
    top, pitch = 8.0, 3.05
    bottom = top + pitch * len(ROWS)

    # Rows: MAVRA's row on a tint, labels in the method's ink.
    for i, m in enumerate(ROWS):
        y = top + pitch * (i + .5)
        if m == 'metric-global-exref':
            s.rect(0, y - pitch / 2, W, pitch, ACC_PALE, None)
        label, color = labels[i]
        s.rect(0, y - .8, 1.6, 1.6, color, None, r=.2)
        text(2.4, y + .75, label, LABEL, INK)

    for j, group in enumerate(GROUPS):
        x0 = left + j * (width + gap)
        x = Scale(0, 100, x0 + .6, x0 + width - .6)
        for v in (0, 25, 50, 75, 100):
            s.line(x(v), top, x(v), bottom, GRID if v % 50 else RULE, .14 if v % 50 else .18)
        s.line(x0, bottom, x0 + width, bottom, MUTED, .16)
        for v, align, dx in ((0, 'left', -.45), (50, 'center', 0), (100, 'right', .45)):
            s.line(x(v), bottom, x(v), bottom + .7, MUTED, .16)
            text(x(v) + dx, bottom + 3.0, str(v), TICK, MUTED, align=align)
        first, second = TITLES[lang][j]
        if first:
            text(x0 + width / 2, 3.1, first, TITLE, INK, 'bold', 'center', width=width + gap)
        text(x0 + width / 2, 6.0, second, TITLE, INK, 'bold', 'center', width=width + gap)
        for i, m in enumerate(ROWS):
            y = top + pitch * (i + .5)
            acc, lo, hi = rows[m][j]
            _, color = style.method(m, lang)
            if hi - lo > .05:
                s.line(x(lo), y, x(hi), y, color, .42)
            s.marker(x(acc), y, 'circle', 1.45, color, WHITE, .14)

    text((left + right) / 2, H - .9, AXIS[lang], LABEL, MUTED, align='center')


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
