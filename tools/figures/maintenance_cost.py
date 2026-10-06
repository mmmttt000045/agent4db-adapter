"""Figure 3: maintenance database time relative to definition-level revalidation.

Two panels (staggered and simultaneous arrivals) share the y axis; series are
labelled on the lines instead of in a legend. Data:
exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json, the archive that
tools/review-results.py turns into the \\Cb* macros; the 4- and 19-definition
points are checked against those macros.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import Scale  # noqa: E402
import style  # noqa: E402
from style import GRID, INK, MUTED, ORANGE, WHITE  # noqa: E402

NAME = 'maintenance-cost'
W, H = style.COLUMN, 44.0
DATA = style.ROOT / 'exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json'

ARRIVALS = [('staggered', 'Stag'), ('burst', 'Burst')]
# policy -> (macro key, line dash, marker), in drawing order: the cache comes last with
# hollow triangles, so it stays visible where it coincides with MAVRA.
SERIES = {'condition-scope': ('Scope', (.25, .55), 'square'),
          'condition': ('Cond', None, 'circle'),
          'definition-cache': ('Cache', (1.1, .6), 'triangle')}
SHARES = (1, 2, 4, 6)
TEXT = {
    'en': {'y': 'DB time vs. definition-level', 'x': 'Definitions',
           'panels': ('Staggered', 'Simultaneous')},
    'zh': {'y': '相对定义级的 DB 时间', 'x': '定义数', 'panels': ('错峰', '同时到达')},
}
LABEL, TICK, TITLE = 6.5, 6.0, 7.0     # font sizes, pt (acmart \scriptsize is 6, \footnotesize 7)


def load():
    rows = json.loads(DATA.read_text(encoding='utf-8'))['rows']
    printed = style.macros('review')
    series = {}
    for arrival, akey in ARRIVALS:
        for policy, (pkey, _, _) in SERIES.items():
            pts = []
            for share in SHARES:
                row = next(r for r in rows if r['share'] == share and r['arrival'] == arrival
                           and r['policy'] == policy)
                pts.append((row['specs'], 100 * row['vs_definition']))
                if share in (1, 6):
                    name = f"Cb{akey}{pkey}{'One' if share == 1 else 'Six'}"
                    style.agree(name, f'{100 * row["vs_definition"]:.1f}', printed[name])
            series[arrival, policy] = pts
    return series


def draw(s, lang):
    series, T, text = load(), TEXT[lang], s.text
    top, bottom = 9.6, 34.2
    y = Scale(0, 125, bottom, top)
    panels = [(8.8, 45.0), (48.2, W - .4)]

    text(0, 2.7, T['y'], LABEL, MUTED)
    for v in (0, 25, 50, 75, 100):
        text(panels[0][0] - 1.0, y(v) + .7, f'{v}%', TICK, MUTED, align='right')

    for k, ((arrival, _), (x0, x1)) in enumerate(zip(ARRIVALS, panels)):
        x = Scale(2, 21, x0, x1)
        text((x0 + x1) / 2, 6.8, T['panels'][k], TITLE, INK, 'bold', 'center')
        for v in (25, 50, 75, 100, 125):
            s.line(x0, y(v), x1, y(v), GRID, .14)
        s.line(x0, y(0), x1, y(0), MUTED, .16)
        for d in (4, 8, 15, 19):
            s.line(x(d), y(0), x(d), y(0) + .7, MUTED, .16)
            text(x(d), bottom + 3.1, str(d), TICK, MUTED, align='center')
        # Definition-level revalidation is the 100% reference.
        s.line(x0, y(100), x1, y(100), ORANGE, .32, dash=(.35, .55))
        for policy, (_, dash, kind) in SERIES.items():
            label, color = style.method(policy, lang)
            pts = [(x(d), y(v)) for d, v in series[arrival, policy]]
            s.poly(pts, None, color, .34, closed=False, dash=dash)
            for px, py in pts:
                if kind == 'triangle':
                    s.marker(px, py, kind, 1.45, None, color, .22)
                else:
                    s.marker(px, py, kind, 1.35, color, WHITE, .12)

        if k == 0:
            # Labels sit where the staggered lines are far apart.
            text(x0 + .8, y(100) - 1.0, style.method('definition', lang)[0], LABEL, ORANGE)
            scope, scope_color = style.method('condition-scope', lang)
            text(x(9.2), y(88.6), scope, LABEL, scope_color)
            cache, cache_color = style.method('definition-cache', lang)
            text(x(4) + 1.4, y(59), cache, LABEL, cache_color)
            mavra, mavra_color = style.method('condition', lang)
            text(x(19.4), y(2), mavra, LABEL, mavra_color, 'bold', 'right')

    text((panels[0][0] + panels[1][1]) / 2, H - .9, T['x'], LABEL, MUTED, align='center')


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
