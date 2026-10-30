"""Multiple independent agents repeat schema, value and join exploration.

Keep the original three-lane icon composition. Richer native vector glyphs
depict LLM agents, tool workbenches and a shared database without repeating
prose in each lane. Agents 1, 2 and N are drawn explicitly; ellipses represent
additional agents, their workbenches and database traffic. The probe order,
sampling, column inspection, revisits and candidate join tests differ by
lane. These are conceptual UIs, not screenshots or measured traces.
Table and field names follow tools/figures/example.py and
src/metricbench.rs. Packet and path counts are illustrative.
"""
import math
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vecfig  # noqa: E402
import style  # noqa: E402
from vecfig import MM, PT  # noqa: E402

NAME = 'metric-record'
W, H = style.COLUMN, 76.7

INK = '#332E40'
MUTED = '#81798D'
EDGE = '#A6A0AE'
RULE = '#DCD5EA'
WHITE = '#FFFFFF'
VIOLET = '#8069B6'
DEEP = '#5C478D'
PALE = '#F4F0FA'
MID = '#D8CBEF'
AMBER = '#C68E35'
AMBER_PALE = '#FBEDCE'
DB_FACE = '#F6F5F8'
LOAD = '#BD533E'
LOAD_PALE = '#FBE7DF'

LABELS = {
    'en': {
        'questions': ('Mar revenue?', 'Sep revenue?', 'Q3 revenue?'),
        'database': 'Database',
    },
    'zh': {
        'questions': ('3 月营业额？', '9 月营业额？', 'Q3 营业额？'),
        'database': '数据库',
    },
}


@contextmanager
def windows_fonts_if_needed():
    """Use Windows fonts when this machine has no TeX font locator.

    The normal paper build keeps the project's Biolinum, Inconsolata and Noto
    fonts. Limit this fallback to this figure so building other figures is not
    affected.
    """
    font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    paths = {
        'biolinum': font_dir / 'arial.ttf',
        'biolinum-bold': font_dir / 'arialbd.ttf',
        'inconsolata': font_dir / 'consola.ttf',
        'cjk': font_dir / 'msyh.ttc',
        'cjk-bold': font_dir / 'msyhbd.ttc',
    }
    if os.name != 'nt' or shutil.which('kpsewhich') or not all(p.exists() for p in paths.values()):
        yield
        return
    previous = {name: vecfig.FONTS[name] for name in paths}
    try:
        for name, path in paths.items():
            vecfig.FONTS[name] = vecfig.Font(lambda p=str(path): (p, 0))
        yield
    finally:
        vecfig.FONTS.update(previous)


def draw(s, lang):
    with windows_fonts_if_needed():
        _draw(s, lang)


def _draw(s, lang):
    L = LABELS[lang]

    def label(x, y, text, size=7.4, color=INK, weight='sans', align='center', width=None):
        s.text(x, y + .34 * size * PT, text, size, color, weight, align, width)

    def arrow(points, color=VIOLET, sw=.23, heads='end', dash=None):
        s.route(points, color, sw, heads=heads, dash=dash, radius=.5, length=.9)

    def ellipsis(x, y, color=VIOLET):
        # Native dots keep the omission mark consistent across Latin/CJK fonts.
        for offset in (-1.15, 0, 1.15):
            s.circle(x + offset, y, .34, color)

    def ellipse(x, y, w, h, fill=None, stroke=None, sw=.2):
        c = s.c
        c.saveState()
        s._style(fill, stroke, sw)
        c.ellipse(x * MM, (H - y - h) * MM, (x + w) * MM, (H - y) * MM,
                  stroke=stroke is not None, fill=fill is not None)
        c.restoreState()

    def table(x, y, w, h, cols=3, rows=3, focus=None, ink=VIOLET, column=None):
        """A grid with a header and an optional highlighted cell or column."""
        hh = h * .26
        s.rect(x, y, w, h, WHITE, ink, .19, r=.25)
        s.rect(x + .15, y + .15, w - .3, hh - .15, MID)
        dy = (h - hh) / rows
        if column is not None:
            s.rect(x + w * column / cols + .08, y + hh + .05,
                   w / cols - .16, h - hh - .1, AMBER_PALE)
        if focus is not None:
            col, row = focus
            s.rect(x + w * col / cols + .08, y + hh + dy * row + .05,
                   w / cols - .16, dy - .1, AMBER_PALE)
        for col in range(1, cols):
            s.line(x + col * w / cols, y + hh, x + col * w / cols, y + h, ink, .12)
        for row in range(rows):
            yy = y + hh + row * dy
            s.line(x, yy, x + w, yy, ink, .12)

    def agent_icon(x, y):
        # Neural head + console on the torso + a tool-call bubble: an LLM
        # agent, extending the original head-and-shoulders silhouette.
        hx = x - 1.5
        s.poly([(hx - 3.9, y + 7.6), (hx - 3.5, y + 5.9),
                (hx - 1.9, y + 5.0), (hx + 1.9, y + 5.0),
                (hx + 3.5, y + 5.9), (hx + 3.9, y + 7.6)],
               VIOLET, DEEP, .21)
        s.circle(hx, y + 2.7, 2.25, PALE, DEEP, .24)
        nodes = ((hx - 1.1, y + 2.4), (hx, y + 1.6),
                 (hx + 1.1, y + 2.5), (hx, y + 3.6))
        for a, b in ((0, 1), (1, 2), (0, 3), (2, 3), (1, 3)):
            s.line(*nodes[a], *nodes[b], VIOLET, .17)
        for nx, ny in nodes:
            s.circle(nx, ny, .29, DEEP)
        s.rect(hx - 1.9, y + 5.55, 3.8, 1.65, DEEP, None, r=.3)
        s.poly([(hx - 1.1, y + 5.95), (hx - .65, y + 6.3),
                (hx - 1.1, y + 6.65)], None, WHITE, .18, closed=False)
        s.line(hx - .2, y + 6.65, hx + 1.05, y + 6.65, WHITE, .17)

        # Tool request window; its tail points back to the agent.
        bx, by = x + 2.1, y + 1.5
        s.poly([(bx + .9, by + 3.7), (bx + .5, by + 4.8),
                (bx + 2.5, by + 3.7)], WHITE, VIOLET, .17)
        s.rect(bx, by, 5.5, 3.9, WHITE, VIOLET, .2, r=.55)
        s.line(bx + .3, by + 1.1, bx + 5.2, by + 1.1, RULE, .15)
        for dx in (.7, 1.4):
            s.circle(bx + dx, by + .6, .16, VIOLET)
        s.poly([(bx + .75, by + 1.7), (bx + 1.3, by + 2.15),
                (bx + .75, by + 2.6)], None, DEEP, .19, closed=False)
        s.line(bx + 1.9, by + 2.05, bx + 4.6, by + 2.05, VIOLET, .2)
        s.line(bx + 1.9, by + 2.9, bx + 3.8, by + 2.9, VIOLET, .17)

    def schema_icon(x, y, variant=0):
        if variant == 1:
            # Inspect one column's metadata rather than a two-table overview.
            table(x - 6.4, y - 2.7, 8.6, 5.3, cols=4, column=2)
            arrow([(x + 2.4, y), (x + 3.8, y)], VIOLET, .17)
            s.rect(x + 4.1, y - 2.25, 4.7, 4.65, WHITE, VIOLET, .18, r=.3)
            s.line(x + 4.3, y - .1, x + 8.6, y - .1, RULE, .14)
            s.circle(x + 5.3, y - 1.15, .35, WHITE, DEEP, .17)
            s.line(x + 5.65, y - 1.15, x + 7.6, y - 1.15, DEEP, .17)
            label(x + 6.45, y + 1.1, '#', 6.5, DEEP, 'code')
            return
        if variant == 2:
            # Browse a small catalog, then expand one table's columns.
            for yy in (y - 2.65, y + .45):
                table(x - 6.4, yy, 4.7, 2.5, cols=2, rows=1)
            arrow([(x - 1.4, y + 1.65), (x, y + 1.65),
                   (x, y), (x + 1.0, y)], VIOLET, .17)
            table(x + 1.3, y - 2.2, 7.5, 5.0, cols=3, column=2)
            return
        table(x - 6.4, y - 2.7, 8.1, 5.3, focus=(0, 0))
        table(x + 4.0, y - 1.4, 4.8, 3.9, cols=2, rows=2)
        # A key/foreign-key reference between two schema objects.
        s.circle(x - 5.0, y - .4, .37, WHITE, DEEP, .17)
        arrow([(x + 1.8, y - .3), (x + 2.8, y - .3),
               (x + 2.8, y + 1.1), (x + 3.7, y + 1.1)], VIOLET, .17)

    def value_icon(x, y, variant=0):
        if variant == 1:
            # Re-sample and compare two result slices after a join probe.
            table(x - 6.4, y - 2.5, 5.7, 5.0, cols=2, rows=3, focus=(1, 2))
            table(x + .7, y - 2.5, 5.7, 5.0, cols=2, rows=2, focus=(0, 0))
            s.route([(x - .5, y), (x + .5, y)], VIOLET, .17, length=.6)
            s.line(x + 7.4, y + 1.35, x + 8.65, y + 2.6, DEEP, .4)
            s.circle(x + 6.4, y + .3, 1.5, WHITE, DEEP, .23)
            s.rect(x + 5.65, y - .2, 1.5, 1.0, AMBER_PALE, AMBER, .15, r=.1)
            return
        if variant == 2:
            # Enumerate a period column. 7/8/9 illustrate the Q3 predicate,
            # not observed result cardinalities or a measured execution trace.
            table(x - 6.4, y - 2.65, 4.7, 4.0, cols=2, rows=3, column=1)
            s.poly([(x - 1.25, y - 2.0), (x + .85, y - 2.0),
                    (x + .1, y - .7), (x + .1, y + .45),
                    (x - .5, y + .85), (x - .5, y - .7)],
                   WHITE, VIOLET, .18)
            for cx, month in zip((x + 2.2, x + 4.75, x + 7.3), ('7', '8', '9')):
                s.rect(cx - 1.1, y - 1.5, 2.2, 2.5, AMBER_PALE, AMBER, .17, r=.25)
                label(cx, y - .25, month, 6.5, INK, 'code')
            label(x + 1.2, y + 2.4, 'DISTINCT', 6.5, DEEP, 'code', width=16)
            return

        # Sample a few values, zoom one cell, then continue to the join test.
        table(x - 6.4, y - 2.7, 10.0, 4.1, cols=3, rows=2, focus=(2, 1))
        s.line(x + 5.25, y - .1, x + 7.3, y + 1.65, DEEP, .48)
        s.circle(x + 4.1, y - 1.15, 1.75, WHITE, DEEP, .25)
        s.rect(x + 3.2, y - 1.75, 1.8, 1.2, AMBER_PALE, AMBER, .16, r=.12)
        s.line(x + 3.55, y - 1.3, x + 4.65, y - 1.3, AMBER, .18)
        label(x + .9, y + 2.4, 'LIMIT', 6.5, DEEP, 'code', width=16)

    def join_icon(x, y, variant=0):
        if variant == 1:
            # Test join cardinality, then revisit the sampled values.
            table(x - 6.4, y - 2.7, 4.3, 3.7, cols=2, rows=2, focus=(1, 0))
            table(x + .5, y - 2.15, 4.3, 3.7, cols=2, rows=2, focus=(0, 1))
            s.line(x - 2.0, y - .6, x - 1.6, y - .6, VIOLET, .2)
            s.line(x - .1, y - .6, x + .4, y - .6, VIOLET, .2)
            s.poly([(x - 1.6, y - 1.3), (x - .1, y + .1),
                    (x - .1, y - 1.3), (x - 1.6, y + .1)], WHITE, DEEP, .19)
            s.route([(x + 5.0, y - .6), (x + 5.8, y - .6)], VIOLET, .17, length=.55)
            s.rect(x + 6.0, y - 1.8, 2.8, 2.6, WHITE, VIOLET, .18, r=.25)
            label(x + 7.4, y - .5, '#', 6.5, DEEP, 'code')
            label(x + 1.0, y + 2.65, 'COUNT(*)', 6.5, DEEP, 'code', width=16)
            return
        if variant == 2:
            # Compare alternative key alignments, without asserting outcomes.
            table(x - 6.4, y - 2.6, 4.8, 5.1, cols=2, rows=3, focus=(1, 0))
            table(x + 4.0, y - 2.6, 4.8, 5.1, cols=2, rows=3, focus=(0, 2))
            for yy, offset, dash in ((y - .7, -1.5, (.45, .4)),
                                     (y + 1.3, 1.6, None)):
                for points in ([(x - 1.5, yy), (x - .6, y + offset),
                                (x + .5, y + offset)],
                               [(x + 1.7, y + offset), (x + 3.0, y + offset),
                                (x + 3.85, yy)]):
                    s.poly(points, None, VIOLET, .2, closed=False, dash=dash)
                s.poly([(x + .5, y + offset - .6), (x + 1.7, y + offset + .6),
                        (x + 1.7, y + offset - .6), (x + .5, y + offset + .6)],
                       WHITE, DEEP, .18)
            return
        table(x - 6.4, y - 2.7, 4.8, 4.9, cols=2, rows=3, focus=(1, 1))
        table(x + 4.0, y - 1.8, 4.8, 4.9, cols=2, rows=3, focus=(0, 1))
        # Matching key ports connect through a join operator.
        s.line(x - 1.5, y + .5, x + .1, y + .5, VIOLET, .23)
        s.line(x + 1.65, y + .5, x + 2.9, y + .5, VIOLET, .23)
        s.line(x + 2.9, y + .5, x + 2.9, y + 1.35, VIOLET, .23)
        s.line(x + 2.9, y + 1.35, x + 3.9, y + 1.35, VIOLET, .23)
        s.poly([(x + .1, y - .35), (x + 1.65, y + 1.35),
                (x + 1.65, y - .35), (x + .1, y + 1.35)], WHITE, DEEP, .2)
        s.circle(x - 2.75, y + .5, .3, AMBER)
        s.circle(x + 5.15, y + 1.35, .3, AMBER)

    centers = (14.3, 41.1, 70.3)
    # Vary operations as well as their order: sampling then a key test;
    # column metadata then a count-based join check and re-sampling; and
    # value enumeration then catalog browsing and candidate join comparison.
    # These are representative trajectories, not transcriptions of sessions.
    plans = (((schema_icon, 0), (value_icon, 0), (join_icon, 0)),
             ((schema_icon, 1), (join_icon, 1), (value_icon, 1)),
             ((value_icon, 2), (schema_icon, 2), (join_icon, 2)))
    for lane, (x, agent, question, plan) in enumerate(zip(centers, ('1', '2', 'N'),
                                                        L['questions'], plans)):
        agent_icon(x, .5)
        label(x, 10.4, 'Agent ' + agent, 7.5, DEEP, 'bold', width=24)
        s.rect(x - 11.1, 13.0, 22.2, 4.7, WHITE, RULE, .18, r=.7)
        label(x, 15.35, question, 6.8, INK, width=21)
        arrow([(x, 18.1), (x, 19.8)])

        # Common workbench chrome; individual trajectories occupy its rows.
        s.rect(x - 11.1, 20.2, 22.2, 26.5, PALE, VIOLET, .24, r=.8)
        s.line(x - 10.7, 22.5, x + 10.7, 22.5, RULE, .17)
        for dx in (-9.4, -8.2, -7.0):
            s.circle(x + dx, 21.4, .23, VIOLET)
        s.line(x + 6.7, 21.4, x + 9.3, 21.4, VIOLET, .17)
        s.line(x - 9.2, 26.3, x - 9.2, 42.0, RULE, .24)
        for yy in (30.1, 37.9):
            s.head(x - 9.2, yy, math.pi / 2, VIOLET, .65)
        if lane > 0:
            # Revisit an earlier test: values -> join for Agent 2, and
            # schema -> values for Agent N, instead of identical pipelines.
            source, target = (41.7, 34.0) if lane == 1 else (34.0, 26.3)
            s.curve((x - 9.75, source), (x - 10.8, source),
                    (x - 10.8, target), (x - 9.75, target),
                    VIOLET, .17, (.45, .4))
            s.head(x - 9.75, target, 0, VIOLET, .55)
        for y in (26.3, 34.0, 41.7):
            s.circle(x - 9.2, y, .55, WHITE, VIOLET, .2)
        for yy, (operation, variant) in zip((26.3, 34.0, 41.7), plan):
            operation(x + .3, yy, variant)
        for y in (30.2, 38.0):
            s.line(x - 6.5, y, x + 9.0, y, RULE, .13)

    # Show a population of agents without adding more full-size UI lanes.
    # Aligned omission marks cover the agent and its entire exploration path.
    omission_x = (centers[1] + centers[2]) / 2
    ellipsis(omission_x, 10.4, DEEP)
    ellipsis(omission_x, 34.0)

    # Give the database enough depth to show the actual shared relations,
    # join keys and repeatedly explored columns. All traffic targets this one
    # relation group; there are no private per-agent tables in this layer.
    x, y, w, h, rim = 1.6, 59.2, 81.4, 16.5, 2.1
    s.rect(x, y + rim / 2, w, h - rim, DB_FACE)
    ellipse(x, y + h - rim, w, rim, DB_FACE, EDGE, .22)
    s.rect(x + .12, y + rim / 2, w - .24, h - rim, DB_FACE)
    s.line(x, y + rim / 2, x, y + h - rim / 2, EDGE, .22)
    s.line(x + w, y + rim / 2, x + w, y + h - rim / 2, EDGE, .22)
    ellipse(x, y, w, rim, WHITE, EDGE, .22)

    # Warm emphasis is reserved for redundant traffic and repeated reads.
    s.rect(26.8, 59.6, 32.0, 1.35, LOAD_PALE, LOAD, .19, r=.55)
    label(W / 2, 63.0, L['database'], 7.5, INK, 'bold', width=77)
    tables = ((7.2, 'store_sales', ('ss_sold_date_sk', 'ss_net_paid')),
              (47.3, 'date_dim', ('d_date_sk', 'd_moy')))
    for tx, name, fields in tables:
        ty, tw, th, hh = 65.1, 30.1, 8.6, 2.7
        s.rect(tx, ty, tw, th, WHITE, VIOLET, .21, r=.35)
        s.rect(tx + .13, ty + .13, tw - .26, hh - .13, PALE)
        label(tx + tw / 2, ty + hh / 2, name, 6.7, DEEP, 'code', width=tw - 1.6)
        # The repeated value-probe target is highlighted in both tables.
        s.rect(tx + .13, ty + 5.65, tw - .26, 2.8, AMBER_PALE)
        for yy in (ty + hh, ty + 5.6):
            s.line(tx, yy, tx + tw, yy, RULE, .16)
        s.line(tx + 3.5, ty + hh, tx + 3.5, ty + th, RULE, .14)
        for row, field in enumerate(fields):
            yy = ty + 4.12 + 2.9 * row
            label(tx + 4.5, yy, field, 6.5, INK, 'code', 'left', tw - 5.4)
            if row == 0:
                s.circle(tx + 1.35, yy - .15, .42, WHITE, DEEP, .16)
                s.line(tx + 1.75, yy - .15, tx + 2.6, yy - .15, DEEP, .17)
                s.line(tx + 2.25, yy - .15, tx + 2.25, yy + .3, DEEP, .16)
            else:
                for col, height in enumerate((.7, 1.1, .9)):
                    s.rect(tx + .9 + col * .65, yy + .55 - height,
                           .38, height, AMBER)
                # Several reads hit the same highlighted field, rather than
                # implying separate per-agent partitions of the database.
                for dy in (-.8, 0, .8):
                    s.route([(tx + 28.8, yy + dy), (tx + 23.8, yy + dy)],
                            LOAD, .16, length=.65)

    # The two relations form the same join target for every agent.
    s.line(37.5, 69.25, 40.7, 69.25, VIOLET, .24)
    s.line(43.9, 69.25, 47.1, 69.25, VIOLET, .24)
    s.poly([(40.7, 68.1), (43.9, 70.4), (43.9, 68.1), (40.7, 70.4)],
           WHITE, DEEP, .22)

    def traffic(sx, tx, returning=False, phase=0):
        """A separate request stream with packets; streams never coalesce."""
        p0, p1 = (sx, 47.1), (sx, 51.7)
        p2, p3 = (tx, 55.8), (tx, 60.25)
        color = VIOLET if returning else LOAD
        sw = .22 if returning else .38
        s.curve(p0, p1, p2, p3, color, sw, (.65, .55) if returning else None)
        end = p0 if returning else p3
        s.head(*end, -math.pi / 2 if returning else math.pi / 2,
               color, .95 if returning else 1.15)
        # Packet outlines make repeated transfers visible without adding text.
        for t in ((.36, .70) if returning else (.23 + phase, .59 + phase)):
            u = 1 - t
            px = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
            py = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
            dx = 3*u*u*(p1[0]-p0[0]) + 6*u*t*(p2[0]-p1[0]) + 3*t*t*(p3[0]-p2[0])
            dy = 3*u*u*(p1[1]-p0[1]) + 6*u*t*(p2[1]-p1[1]) + 3*t*t*(p3[1]-p2[1])
            norm = math.hypot(dx, dy)
            ax, ay, bx, by = dx/norm*.68, dy/norm*.68, -dy/norm*.38, dx/norm*.38
            s.poly([(px-ax-bx, py-ay-by), (px+ax-bx, py+ay-by),
                    (px+ax+bx, py+ay+by), (px-ax+bx, py-ay+by)],
                   WHITE, color, .19)

    # Nine illustrative probe streams arrive at one hotspot; each session has
    # its own return stream. Draw after the DB so ingress arrowheads stay clear.
    for x, target in zip(centers, (30.2, 41.6, 53.0)):
        for index, offset in enumerate((-1.1, 0.0, 1.1)):
            traffic(x - 1.3 + 1.7 * (index - 1), target + offset,
                    phase=.035 * index)
        traffic(x + 4.5, target + 3.0, returning=True)

    ellipsis(omission_x, 50.4, LOAD)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
