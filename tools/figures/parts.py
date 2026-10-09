"""Drawing parts for the three system figures of the report deck (overview,
lookup, lifecycle).

The figures are drawn at slide size (300 mm wide, 12-15 pt text), not at the
paper's 6 pt: they go into a PPT. Every function takes the vecfig Sheet first;
coordinates are millimetres from the top-left, font sizes points. The look
follows the paper's architecture figure: 3D nodes for agents and the database,
boxes with a bold title and a muted note, step badges and arrows coloured by
path, thin arrows for calls, thick ones for writes to the metric store, dashed
ones for reads of database state.
"""
import math

from vecfig import PT, measure
from style import ACC, AMBER, AMBER_PALE, EDGE, FACE, INK, MUTED, RED, WHITE

K = 2.0                                          # geometry relative to the paper figure
TITLE, BODY, NOTE, STEP = 15.0, 13.0, 12.0, 11.0  # pt
LEARN, USE, EXEC = '#7A68B0', ACC, '#C97A1E'     # path colours: learning, lookup, execution
THIN, THICK = .45, 1.0                            # call or response; write to the metric store
DASH = (1.8, 1.2)                                 # read of database state
HEAD = 2.6                                        # arrowhead length
WAIT = '#9A6500'                                  # text on amber: missing result, changed version
SOFT = '#BDB9B2'                                  # edges of grey 3D nodes
PANEL_EDGE = '#9DBBE2'


def baseline(y_center, size):
    """Baseline that centres capitals and digits on y_center."""
    return y_center + .34 * size * PT


def box(s, b, fill=WHITE, stroke=EDGE, sw=.3, dash=None):
    s.rect(*b, fill, stroke, sw, r=1.2, dash=dash)


def titled(s, b, title, note=None, pad=3.0, fill=WHITE, stroke=EDGE):
    """Box with a bold title and a muted note."""
    x, y, w, h = b
    box(s, b, fill, stroke)
    s.text(x + pad, y + 7.0, title, TITLE, INK, 'bold', width=w - 2 * pad)
    if note:
        s.text(x + pad, y + 13.0, note, NOTE, MUTED, width=w - 2 * pad)


def step(s, x, y, n, color, r=3.0):
    s.circle(x, y, r, color)
    s.text(x, baseline(y, STEP), str(n), STEP, WHITE, 'bold', 'center')


def mark(s, x, y, kind):
    """Result mark centred on (x, y): holds, fails, or not yet known."""
    if kind == 'ok':
        s.poly([(x - 1.25, y), (x - .3, y + 1.0), (x + 1.3, y - 1.1)], None, ACC, .5, closed=False)
    elif kind == 'fail':
        s.line(x - 1.0, y - 1.0, x + 1.0, y + 1.0, RED, .5)
        s.line(x - 1.0, y + 1.0, x + 1.0, y - 1.0, RED, .5)
    else:
        s.text(x, y + 1.6, '?', NOTE + 1, WAIT, 'bold', 'center')


def node(s, b, d=3.0):
    """A grey 3D node: front face with a top and a right face behind it."""
    x, y, w, h = b
    s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], '#F2F0EC', SOFT, .25)
    s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
           '#E7E4DF', SOFT, .25)
    s.rect(x, y, w, h, WHITE, SOFT, .3, r=.8)


def person(s, x, y, color='#8E8B85'):
    """Head and shoulders, (x, y) the top-left of a 5 x 7 mm glyph."""
    s.circle(x + 2.5, y + 1.7, 1.7, color)
    s.rect(x, y + 3.8, 5.0, 3.0, color, None, r=1.5)


def sparkle(s, cx, cy, r, color=WHITE):
    """Four-pointed star, the usual mark for an LLM."""
    pts = []
    for k in range(8):
        a = math.pi / 4 * k - math.pi / 2
        rr = r if k % 2 == 0 else .28 * r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    s.poly(pts, color, None)


def llm_badge(s, cx, cy, r=3.6):
    """The built-in agent is an LLM: blue tile with a sparkle."""
    s.rect(cx - r, cy - r, 2 * r, 2 * r, ACC, None, r=.5 * r)
    sparkle(s, cx, cy, .7 * r)
    sparkle(s, cx + .58 * r, cy - .55 * r, .25 * r)


def slab(s, b, d=2.8):
    """The SQL database: one grey storage slab."""
    x, y, w, h = b
    s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], '#F2F0EC', SOFT, .25)
    s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
           '#E7E4DF', SOFT, .25)
    s.rect(x, y, w, h, FACE, SOFT, .3, r=1.0)


def table_card(s, x0, w, y0, h, label='', changed=(), outline=EDGE, dash=None, size=NOTE - 1):
    """A table drawn as a card with a header and rows; changed rows are amber."""
    s.rect(x0, y0, w, h, WHITE, outline, .28, r=.7, dash=dash)
    s.rect(x0 + .3, y0 + .3, w - .6, 4.6, '#ECEAE5', None, r=.5)
    if label:
        s.text(x0 + w / 2, y0 + 3.9, label, size, INK, align='center', width=w - .8)
    rows = int((h - 6.2) // 2.6)
    for r_ in range(rows):
        yy = y0 + 6.0 + 2.6 * r_
        hot = r_ in changed
        s.rect(x0 + 1.5, yy, w - 3.0, 1.5, AMBER_PALE if hot else '#E4E1DB',
               AMBER if hot else None, .2, r=.4)


def legend_pill(s, x, y, label, color, steps='', dashed=False):
    """One legend entry: a coloured pill (with the step range) and its label; returns its width."""
    w = 13.0
    if dashed:
        s.rect(x, y - 2.8, w, 5.6, WHITE, color, .35, r=2.8, dash=(1.6, 1.0))
    else:
        s.rect(x, y - 2.8, w, 5.6, color, None, r=2.8)
    if steps:
        s.text(x + w / 2, baseline(y, STEP), steps, STEP, WHITE, 'bold', 'center')
    s.text(x + w + 2.4, baseline(y, NOTE), label, NOTE, INK)
    return w + 2.4 + measure(label, NOTE)


def legend_line(s, x, y, label, sw, color, dash=None):
    """One line-kind legend entry; returns its width."""
    s.route([(x, y), (x + 13.0, y)], color, sw, dash=dash, length=HEAD)
    s.text(x + 15.4, baseline(y, NOTE), label, NOTE, MUTED)
    return 15.4 + measure(label, NOTE)


def stage(s, b, n, color, title, note, edge=PANEL_EDGE, dash=None, badge=True):
    """A step box: badge, bold title, a muted note, then a tinted area for the example.

    n=None draws the other outcome's red badge with a cross; badge=False draws no
    badge (a box the steps pass through without a number of its own); note=None
    starts the example area right under the title.
    Returns (x, y, w) for the example rows: left edge, first baseline, room.
    """
    x, y, w, h = b
    s.rect(*b, WHITE, edge, .4, r=1.6, dash=dash)
    tx = x + 9.6
    if not badge:
        tx = x + 3.0
    elif n is None:                              # the other outcome: a red badge with a cross
        s.circle(x + 5.0, y + 5.6, 3.0, RED)
        s.line(x + 3.9, y + 4.5, x + 6.1, y + 6.7, WHITE, .55)
        s.line(x + 3.9, y + 6.7, x + 6.1, y + 4.5, WHITE, .55)
    else:
        step(s, x + 5.0, y + 5.6, n, color)
    s.text(tx, baseline(y + 5.6, TITLE), title, TITLE, color if not badge else INK, 'bold', width=x + w - 1.4 - tx)
    if note is None:
        s.rect(x + 1.8, y + 10.6, w - 3.6, h - 12.2, '#F7F6F3', None, r=1.0)
        return x + 3.6, y + 16.0, w - 7.2
    s.text(x + 3.0, y + 12.6, note, NOTE, MUTED, width=w - 5)
    s.rect(x + 1.8, y + 15.0, w - 3.6, h - 16.6, '#F7F6F3', None, r=1.0)
    return x + 3.6, y + 20.6, w - 7.2


def tag(s, x, y, label, fill='#17233B', size=NOTE - 1):
    """A responsibility tag (publish, rely, maintain and improve): white bold text on a navy pill,
    (x, y) its left edge and vertical centre; returns its width."""
    w = measure(label, size, 'bold') + 4.4
    s.rect(x, y - 2.9, w, 5.8, fill, None, r=1.4)
    s.text(x + 2.2, baseline(y, size), label, size, WHITE, 'bold')
    return w


def rows(s, ex, ey, ew, lines, pitch, first=0, colors=None, marks=None, style='sans'):
    """Example rows: text with an optional colour and a result mark at the right."""
    for k, line in enumerate(lines):
        yy = ey + pitch * (k + first)
        room = ew - (4.6 if marks and k in marks else 0)
        s.text(ex, yy, line, NOTE, (colors or {}).get(k, INK), style, width=room)
        if marks and k in marks:
            mark(s, ex + ew - 1.6, yy - 1.5, marks[k])


__all__ = ['AMBER', 'AMBER_PALE', 'RED']
