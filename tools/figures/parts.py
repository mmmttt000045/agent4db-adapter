"""Drawing parts shared by the three system figures (architecture, lookup, lifecycle).

Every function takes the vecfig Sheet first; coordinates are millimetres from
the top-left at printed size, font sizes points. The look is the one of the
original architecture figure: 3D nodes for agents and the database, boxes with
a bold title and a muted note, step badges and arrows coloured by path, thin
arrows for calls, thick ones for writes to the shared store, dashed ones for
reads of database state.
"""
import math

from vecfig import PT
from style import ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FACE, INK, MUTED, RED, WHITE

TITLE, BODY, NOTE, STEP = 7.0, 6.4, 6.0, 5.6    # pt (acmart \scriptsize is 6, \footnotesize 7)
LEARN, USE, EXEC = '#7A68B0', ACC, '#C97A1E'    # path colours: learning, use, execution
LEARN_PALE, EXEC_PALE = '#EEEAF6', '#FAEBDB'
THIN, THICK = .22, .5                           # call or response; write to the shared store
DASH = (.9, .6)                                 # read of database state
WAIT = '#9A6500'                                # text on amber: no result yet, changed version
SOFT = '#BDB9B2'                                # edges of grey 3D nodes


def baseline(y_center, size):
    """Baseline that centres capitals and digits on y_center."""
    return y_center + .34 * size * PT


def box(s, b, fill=WHITE, stroke=EDGE, sw=.16, dash=None):
    s.rect(*b, fill, stroke, sw, r=.6, dash=dash)


def titled(s, b, title, note=None, pad=1.8, reserve=0, fill=WHITE):
    """Box with a bold title and a muted note; reserve keeps room on the right."""
    x, y, w, h = b
    box(s, b, fill)
    s.text(x + pad, y + 3.6, title, TITLE, INK, 'bold', width=w - 2 * pad - reserve)
    if note:
        s.text(x + pad, y + 6.8, note, NOTE, MUTED, width=w - 2 * pad - reserve)


def step(s, x, y, n, color):
    s.circle(x, y, 1.45, color)
    s.text(x, baseline(y, STEP), str(n), STEP, WHITE, 'bold', 'center')


def mark(s, x, y, kind):
    """Check-result mark centred on (x, y): holds, fails, or not yet known."""
    if kind == 'ok':
        s.poly([(x - .62, y), (x - .15, y + .5), (x + .65, y - .55)], None, ACC, .24,
               closed=False)
    elif kind == 'fail':
        s.line(x - .5, y - .5, x + .5, y + .5, RED, .24)
        s.line(x - .5, y + .5, x + .5, y - .5, RED, .24)
    else:
        s.text(x, y + .8, '?', NOTE + .6, WAIT, 'bold', 'center')


def gate(s, cx, cy, r=2.0, color=ACC):
    """Admission or regression check: candidates pass only between its two bars."""
    s.poly([(cx - r, cy), (cx, cy - r), (cx + r, cy), (cx, cy + r)], WHITE, color, .2)
    for dx in (-.42 * r, .42 * r):
        s.line(cx + dx, cy - .55 * r, cx + dx, cy + .55 * r, color, .24)


def node(s, b, own=False, d=1.5):
    """Front face with a top and a right face behind it; MAVRA's own parts are blue."""
    x, y, w, h = b
    top, side, edge, face = ('#E6EFFA', '#D3E2F4', '#9DBBE2', '#F7FAFE') if own else \
        ('#F2F0EC', '#E7E4DF', SOFT, WHITE)
    s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], top, edge, .12)
    s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
           side, edge, .12)
    s.rect(x, y, w, h, face, ACC if own else edge, .2 if own else .16, r=.5 if own else .35)


def person(s, x, y, color='#8E8B85'):
    """Head and shoulders, (x, y) the top-left of a 2.5 x 3.6 mm glyph."""
    s.circle(x + 1.25, y + .85, .85, color)
    s.rect(x, y + 1.9, 2.5, 1.5, color, None, r=.75)


def sparkle(s, cx, cy, r, color=WHITE):
    """Four-pointed star, the usual mark for an LLM."""
    pts = []
    for k in range(8):
        a = math.pi / 4 * k - math.pi / 2
        rr = r if k % 2 == 0 else .28 * r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    s.poly(pts, color, None)


def llm_badge(s, cx, cy, r=1.8):
    """MAVRA's built-in analysis optimizer is an LLM agent: blue tile with a sparkle."""
    s.rect(cx - r, cy - r, 2 * r, 2 * r, ACC, None, r=.5 * r)
    sparkle(s, cx, cy, .7 * r)
    sparkle(s, cx + .58 * r, cy - .55 * r, .25 * r)


def slab(s, b, d=1.4):
    """The SQL database: one grey storage slab."""
    x, y, w, h = b
    s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], '#F2F0EC', SOFT, .12)
    s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
           '#E7E4DF', SOFT, .12)
    s.rect(x, y, w, h, FACE, SOFT, .16, r=.5)


def table_card(s, x0, w, y0, h, label, changed=(), outline=EDGE, dash=None, size=NOTE):
    """A table drawn as a card with a header and rows; changed rows are amber."""
    s.rect(x0, y0, w, h, WHITE, outline, .14, r=.35, dash=dash)
    s.rect(x0 + .15, y0 + .15, w - .3, 2.0, '#ECEAE5', None, r=.25)
    if label:
        s.text(x0 + w / 2, y0 + 1.7, label, size, INK, align='center', width=w - .4)
    rows = int((h - 2.9) // 1.35)
    for r_ in range(rows):
        yy = y0 + 2.75 + 1.35 * r_
        hot = r_ in changed
        s.rect(x0 + .8, yy, w - 1.6, .78, AMBER_PALE if hot else '#E4E1DB',
               AMBER if hot else None, .1, r=.2)


def chip(s, x, y, label, kind, w=4.4, h=2.3, size=5.4):
    """A condition with its check-result mark."""
    s.rect(x, y, w, h, FACE, EDGE, .1, r=.45)
    s.text(x + .5, y + h - .6, label, size, INK)
    mark(s, x + w - 1.05, y + h / 2, kind)


def pill(s, x, y, label, fill, ink=WHITE, size=NOTE, align='left', pad=1.5, h=2.5):
    """Rounded label; (x, y) is its left (or centre) edge at the vertical middle."""
    from vecfig import measure
    w = measure(label, size, 'bold') + 2 * pad
    x0 = x - w / 2 if align == 'center' else x
    s.rect(x0, y - h / 2, w, h, fill, None, r=h / 2)
    s.text(x0 + w / 2, baseline(y, size), label, size, ink, 'bold', 'center')
    return w


def legend(s, x, y, items, gap=3.8, swatch=6.6):
    """Path legend: [(label, color, steps)] as coloured step-range pills."""
    for k, (label, color, steps) in enumerate(items):
        yy = y + gap * k
        s.rect(x, yy - 1.4, swatch, 2.8, color, None, r=1.4)
        if steps:
            s.text(x + swatch / 2, baseline(yy, STEP), steps, STEP, WHITE, 'bold', 'center')
        s.text(x + swatch + 1.2, baseline(yy, NOTE), label, NOTE, INK)


def line_legend(s, x, y, labels, room, gap=3.8, slate='#5E6E82'):
    """Line kinds: call or response, shared-store write, read of database state."""
    for k, (label, sw, color, dash) in enumerate(zip(labels, (THIN, THICK, THIN),
                                                     (INK, INK, slate), (None, None, DASH))):
        yy = y + gap * k
        s.route([(x, yy), (x + 6.5, yy)], color, sw, dash=dash, length=1.1)
        s.text(x + 8.0, baseline(yy, NOTE), label, NOTE, MUTED, width=room)


__all__ = ['ACC', 'ACC_DK', 'ACC_PALE', 'AMBER', 'AMBER_PALE']
